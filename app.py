import os
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage
from urllib.parse import quote_plus
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error
from werkzeug.utils import secure_filename
import mimetypes
from werkzeug.security import generate_password_hash, check_password_hash

# Load environment variables from .env if present
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24 * 7  # 7 days for static assets

# Optional: gzip compression if Flask-Compress is available
try:
    from flask_compress import Compress  # type: ignore

    Compress(app)
    app.logger.info("Flask-Compress enabled")
except Exception:
    # Safe to ignore if not installed
    pass

# Database configuration from environment
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "company_site"),
}

# Admin credentials are read from environment during login to reflect latest .env values

# File uploads config
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
# Broader set for message/email attachments
ATTACH_ALLOWED_EXTENSIONS = ALLOWED_EXTENSIONS | {"pdf", "txt", "doc", "docx", "xls", "xlsx", "zip"}
UPLOAD_SUBDIR = "uploads"
os.makedirs(os.path.join(app.static_folder, UPLOAD_SUBDIR), exist_ok=True)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_attachment(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ATTACH_ALLOWED_EXTENSIONS


def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        app.logger.error(f"MySQL connection error: {e}")
        return None


@app.after_request
def add_headers(resp):
    """Add caching headers for static assets and security tweaks."""
    try:
        # Cache static assets longer; dynamic routes short/no cache
        if request.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "public, max-age=604800, immutable"  # 7 days
        else:
            # Avoid caching dynamic HTML
            resp.headers.setdefault("Cache-Control", "no-store")
        # Security headers (lightweight)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    except Exception:
        pass
    return resp


def ensure_task_time_logs_table(conn):
    """Create task_time_logs table if it does not exist."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS task_time_logs (
                  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                  employee_id INT UNSIGNED NOT NULL,
                  task_id INT UNSIGNED NOT NULL,
                  action ENUM('start','complete') NOT NULL,
                  at DATETIME NOT NULL,
                  PRIMARY KEY (id),
                  INDEX (employee_id),
                  INDEX (task_id),
                  INDEX (action),
                  CONSTRAINT fk_ttl_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                  CONSTRAINT fk_ttl_emp FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        conn.commit()
    except Error as e:
        app.logger.error(f"ensure_task_time_logs_table error: {e}")


def ensure_auth_logs_table(conn):
    """Create auth_logs table if it does not exist."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_logs (
                  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                  username VARCHAR(100) NULL,
                  user_id INT UNSIGNED NULL,
                  is_admin TINYINT(1) NOT NULL DEFAULT 0,
                  action ENUM('login_success','login_failure','logout') NOT NULL,
                  ip VARCHAR(45) NULL,
                  user_agent VARCHAR(255) NULL,
                  device_type VARCHAR(20) NULL,
                  at DATETIME NOT NULL,
                  PRIMARY KEY (id),
                  INDEX (username),
                  INDEX (user_id),
                  INDEX (is_admin),
                  INDEX (action),
                  INDEX (at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            # Attempt to add device_type if table existed previously without it
            try:
                cur.execute(
                    """
                    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'auth_logs' AND COLUMN_NAME = 'device_type'
                    """
                )
                exists = cur.fetchone()
                if not exists:
                    cur.execute("ALTER TABLE auth_logs ADD COLUMN device_type VARCHAR(20) NULL AFTER user_agent")
            except Exception:
                pass
        conn.commit()
    except Error as e:
        app.logger.error(f"ensure_auth_logs_table error: {e}")


def _detect_device_type(ua: str) -> str:
    """Very simple user-agent based device classifier."""
    if not ua:
        return "unknown"
    s = ua.lower()
    if "mobi" in s or "android" in s or "iphone" in s or "ipad" in s:
        return "mobile"
    return "desktop"


def log_auth_event(action: str, username: str = None, user_id: int = None, is_admin: bool = False):
    """Insert an auth event into auth_logs."""
    conn = get_db_connection()
    if not conn:
        return
    ensure_auth_logs_table(conn)
    try:
        with conn.cursor() as cur:
            ua = request.user_agent.string if request and request.user_agent else None
            cur.execute(
                """
                INSERT INTO auth_logs (username, user_id, is_admin, action, ip, user_agent, device_type, at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    username,
                    user_id,
                    1 if is_admin else 0,
                    action,
                    request.headers.get("X-Forwarded-For", request.remote_addr) if request else None,
                    (ua[:255] if ua else None),
                    _detect_device_type(ua),
                    datetime.utcnow(),
                ),
            )
            conn.commit()
    except Error as e:
        app.logger.error(f"log_auth_event error: {e}")
    finally:
        conn.close()


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please log in to access admin.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapper


def employee_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        # allow admin to access as well
        if session.get("admin_logged_in"):
            return view_func(*args, **kwargs)
        if not session.get("user_id") or session.get("user_role") not in {"employee", "user"}:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("user_login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    # Dynamic homepage stats (override via .env)
    years = int(os.getenv("STATS_YEARS", "8") or 8)
    projects = int(os.getenv("STATS_PROJECTS", "120") or 120)
    uptime = os.getenv("STATS_UPTIME", "99.95%") or "99.95%"
    support = os.getenv("STATS_SUPPORT", "24/7") or "24/7"
    stats = {"years": years, "projects": projects, "uptime": uptime, "support": support}
    # Fetch a few featured services for the homepage hero
    featured_services = []
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT id, title, description, image_filename
                    FROM services
                    WHERE is_active=1
                    ORDER BY featured DESC, sort_order ASC, created_at DESC
                    LIMIT 3
                    """
                )
                featured_services = cur.fetchall()
        except Error as e:
            app.logger.error(f"Home featured services fetch error: {e}")
        finally:
            conn.close()
    return render_template("index.html", stats=stats, featured_services=featured_services)


@app.route("/about")
def about():
    # Show active employees on the about page
    conn = get_db_connection()
    employees = []
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT id, name, position, photo_filename
                    FROM employees
                    WHERE is_active=1
                    ORDER BY sort_order ASC, created_at DESC
                    """
                )
                employees = cur.fetchall()
        except Error as e:
            app.logger.error(f"Employees fetch error: {e}")
        finally:
            conn.close()
    return render_template("about.html", employees=employees)


@app.route("/services")
def services():
    # Public services view: fetch active services
    conn = get_db_connection()
    items = []
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT id, title, description, image_filename, featured, sort_order
                    FROM services
                    WHERE is_active=1
                    ORDER BY featured DESC, sort_order ASC, created_at DESC
                    """
                )
                items = cur.fetchall()
        except Error as e:
            app.logger.error(f"Services fetch error: {e}")
        finally:
            conn.close()
    return render_template("services.html", services=items)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            flash("All fields are required.", "danger")
            return redirect(url_for("contact"))

        conn = get_db_connection()
        if not conn:
            flash("Could not connect to the database. Please try again later.", "danger")
            return redirect(url_for("contact"))

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO contacts (name, email, message, created_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (name, email, message, datetime.utcnow()),
                )
                conn.commit()
            flash("Thank you! Your message has been sent.", "success")
            return redirect(url_for("contact"))
        except Error as e:
            app.logger.error(f"Insert error: {e}")
            flash("An error occurred while sending your message.", "danger")
        finally:
            conn.close()

    return render_template("contact.html")


# ---------------------- User Auth (Employees) ----------------------
@app.route("/register", methods=["GET", "POST"])
def user_register():
    # Public registration disabled; direct to unified sign-in
    flash("Self-registration is disabled. Please contact admin.", "info")
    return redirect(url_for("signin"))


# ---------------------- Admin: Create User ----------------------
@app.route("/admin/users/new", methods=["GET", "POST"])
@admin_required
def admin_users_new():
    conn = get_db_connection()
    employees = []
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT id, name FROM employees WHERE is_active=1 ORDER BY name ASC")
                employees = cur.fetchall()
        except Error as e:
            app.logger.error(f"Employees fetch for user create error: {e}")
        finally:
            conn.close()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        role = (request.form.get("role") or "employee").strip()
        is_active = 1 if request.form.get("is_active") == "on" else 0
        emp_raw = request.form.get("employee_id")
        employee_id = int(emp_raw) if emp_raw and emp_raw.isdigit() else None
        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("admin/user_new.html", employees=employees)
        pw_hash = generate_password_hash(password)
        conn2 = get_db_connection()
        if conn2:
            try:
                with conn2.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO users (username, password_hash, role, is_active, employee_id, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (username, pw_hash, role, is_active, employee_id, datetime.utcnow(), datetime.utcnow()),
                    )
                    conn2.commit()
                flash("User created.", "success")
                return redirect(url_for("admin_users_list"))
            except Error as e:
                app.logger.error(f"User create error: {e}")
                flash("Could not create user (username may be taken).", "danger")
            finally:
                conn2.close()
    return render_template("admin/user_new.html", employees=employees)


@app.route("/login", methods=["GET", "POST"])
def user_login():
    # Backward compatibility: redirect to unified signin with employee preselected
    next_url = request.args.get("next")
    return redirect(url_for("signin", next=next_url))


@app.route("/signin", methods=["GET", "POST"])  # unified login (no role selector)
def signin():
    # Preserve next target (optional). We choose destination after auth.
    next_url = request.args.get("next") or request.form.get("next")
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()

        # First: check if admin via environment credentials
        load_dotenv(override=True)
        env_user = os.getenv("ADMIN_USERNAME", "admin")
        env_pass = os.getenv("ADMIN_PASSWORD", "admin")
        if username == env_user and password == env_pass:
            session.clear()
            session["admin_logged_in"] = True
            flash("Admin logged in.", "success")
            log_auth_event("login_success", username=username, user_id=None, is_admin=True)
            return redirect(next_url or url_for("admin_dashboard"))

        # Else: check regular user in database
        conn = get_db_connection()
        user = None
        if conn:
            try:
                with conn.cursor(dictionary=True) as cur:
                    cur.execute(
                        "SELECT id, username, password_hash, role, is_active, employee_id FROM users WHERE username=%s",
                        (username,),
                    )
                    user = cur.fetchone()
            except Error as e:
                app.logger.error(f"Login fetch error: {e}")
            finally:
                conn.close()

        if not user or not user.get("is_active") or not check_password_hash(user["password_hash"], password):
            flash("Invalid credentials.", "danger")
            # log failure (do not reveal whether admin or user)
            log_auth_event("login_failure", username=username, user_id=None, is_admin=False)
            return redirect(url_for("signin", next=next_url))

        session.clear()
        session["user_id"] = user["id"]
        session["user_role"] = user["role"]
        session["employee_id"] = user.get("employee_id")
        flash("Logged in.", "success")
        log_auth_event("login_success", username=user["username"], user_id=user["id"], is_admin=False)
        return redirect(next_url or url_for("my_tasks"))
    # GET
    return render_template("auth/signin.html", next_url=next_url)


@app.route("/logout")
def user_logout():
    session.pop("user_id", None)
    session.pop("user_role", None)
    session.pop("employee_id", None)
    # try to log logout as user
    try:
        if session.get("admin_logged_in"):
            log_auth_event("logout", username="admin", user_id=None, is_admin=True)
        elif session.get("user_id"):
            log_auth_event("logout", username=None, user_id=session.get("user_id"), is_admin=False)
    except Exception:
        pass
    flash("Logged out.", "info")
    return redirect(url_for("home"))


# ---------------------- Employee: My Tasks ----------------------
@app.route("/my/tasks")
@employee_required
def my_tasks():
    emp_id = session.get("employee_id")
    tasks = []
    if not emp_id:
        flash("Your account is not linked to an employee record.", "warning")
        return render_template("my_tasks.html", tasks=tasks)
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT t.id, t.title, t.description, t.status, t.priority, t.due_date,
                           t.attachment_filename, t.github_url, t.updated_at
                    FROM tasks t
                    WHERE t.employee_id=%s
                    ORDER BY FIELD(t.status,'blocked','in_progress','todo','done'),
                             t.due_date IS NULL, t.due_date ASC, t.updated_at DESC
                    """,
                    (emp_id,),
                )
                tasks = cur.fetchall()
        except Error as e:
            app.logger.error(f"My tasks fetch error: {e}")
        finally:
            conn.close()
    return render_template("my_tasks.html", tasks=tasks)


@app.route("/my/tasks/<int:task_id>")
@employee_required
def my_task_detail(task_id):
    emp_id = session.get("employee_id")
    task = None
    if not emp_id:
        flash("Your account is not linked to an employee record.", "warning")
        return redirect(url_for("my_tasks"))
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT t.id, t.title, t.description, t.status, t.priority, t.due_date, t.created_at, t.updated_at,
                           t.attachment_filename, t.github_url,
                           e.name AS employee_name
                    FROM tasks t
                    LEFT JOIN employees e ON e.id=t.employee_id
                    WHERE t.id=%s AND t.employee_id=%s
                    """,
                    (task_id, emp_id),
                )
                task = cur.fetchone()
        except Error as e:
            app.logger.error(f"My task detail error: {e}")
        finally:
            conn.close()
    if not task:
        flash("Task not found or you do not have access.", "warning")
        return redirect(url_for("my_tasks"))
    return render_template("my_task_detail.html", task=task)


# ---------------------- Public: Completed Projects ----------------------
@app.route("/projects")
def projects():
    """Public page listing completed tasks as projects."""
    rows = []
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT t.id, t.title, t.description, t.updated_at, t.github_url, t.attachment_filename,
                           e.name AS employee_name
                    FROM tasks t
                    LEFT JOIN employees e ON e.id = t.employee_id
                    WHERE t.status = %s
                    ORDER BY t.updated_at DESC
                    LIMIT 50
                    """,
                    ("done",),
                )
                rows = cur.fetchall() or []
        except Error as e:
            app.logger.error(f"Projects fetch error: {e}")
        finally:
            conn.close()
    return render_template("projects.html", tasks=rows)


# ---- Employee: Task time logging (attendance-like) ----
@app.route("/my/tasks/<int:task_id>/start", methods=["POST"])
@employee_required
def task_start(task_id):
    emp_id = session.get("employee_id")
    conn = get_db_connection()
    if not conn:
        flash("Database not available.", "danger")
        return redirect(url_for("my_task_detail", task_id=task_id))
    ensure_task_time_logs_table(conn)
    try:
        with conn.cursor(dictionary=True) as cur:
            # Verify task belongs to employee
            cur.execute("SELECT id, employee_id FROM tasks WHERE id=%s", (task_id,))
            t = cur.fetchone()
            if not t or t.get("employee_id") != emp_id:
                flash("You don't have access to this task.", "danger")
                return redirect(url_for("my_tasks"))
            # Log start and set status to in_progress
            cur.execute(
                "INSERT INTO task_time_logs (employee_id, task_id, action, at) VALUES (%s,%s,%s,%s)",
                (emp_id, task_id, "start", datetime.utcnow()),
            )
            cur.execute(
                "UPDATE tasks SET status=%s, updated_at=%s WHERE id=%s",
                ("in_progress", datetime.utcnow(), task_id),
            )
            conn.commit()
        flash("Task started.", "success")
    except Error as e:
        app.logger.error(f"task_start error: {e}")
        flash("Could not start task.", "danger")
    finally:
        conn.close()
    return redirect(url_for("my_task_detail", task_id=task_id))


@app.route("/my/tasks/<int:task_id>/complete", methods=["POST"])
@employee_required
def task_complete(task_id):
    emp_id = session.get("employee_id")
    conn = get_db_connection()
    if not conn:
        flash("Database not available.", "danger")
        return redirect(url_for("my_task_detail", task_id=task_id))
    ensure_task_time_logs_table(conn)
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT id, employee_id FROM tasks WHERE id=%s", (task_id,))
            t = cur.fetchone()
            if not t or t.get("employee_id") != emp_id:
                flash("You don't have access to this task.", "danger")
                return redirect(url_for("my_tasks"))
            # Log complete and set status to done
            cur.execute(
                "INSERT INTO task_time_logs (employee_id, task_id, action, at) VALUES (%s,%s,%s,%s)",
                (emp_id, task_id, "complete", datetime.utcnow()),
            )
            cur.execute(
                "UPDATE tasks SET status=%s, updated_at=%s WHERE id=%s",
                ("done", datetime.utcnow(), task_id),
            )
            conn.commit()
        flash("Task completed.", "success")
    except Error as e:
        app.logger.error(f"task_complete error: {e}")
        flash("Could not complete task.", "danger")
    finally:
        conn.close()
    return redirect(url_for("my_task_detail", task_id=task_id))


@app.route("/my/activity.json")
@employee_required
def my_activity_json():
    emp_id = session.get("employee_id")
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "db_unavailable"}), 503
    ensure_task_time_logs_table(conn)
    start_day = datetime.utcnow().date() - timedelta(days=6)
    labels = []
    for i in range(7):
        d = start_day + timedelta(days=i)
        labels.append(d.strftime("%Y-%m-%d"))
    data = {d: {"start": 0, "complete": 0} for d in labels}
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                """
                SELECT DATE(at) AS d, action, COUNT(*) AS c
                FROM task_time_logs
                WHERE employee_id=%s AND at >= %s
                GROUP BY DATE(at), action
                ORDER BY DATE(at)
                """,
                (emp_id, start_day),
            )
            for row in cur.fetchall():
                key = row["d"].strftime("%Y-%m-%d")
                if key in data and row["action"] in ("start", "complete"):
                    data[key][row["action"]] = int(row["c"]) or 0
    except Error as e:
        app.logger.error(f"my_activity_json error: {e}")
    finally:
        conn.close()
    return jsonify({
        "labels": labels,
        "start": [data[d]["start"] for d in labels],
        "complete": [data[d]["complete"] for d in labels],
    })


# ---------------------- Admin: Users management ----------------------
@app.route("/admin/users")
@admin_required
def admin_users_list():
    rows = []
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    "SELECT u.id, u.username, u.role, u.is_active, u.employee_id, e.name AS employee_name FROM users u LEFT JOIN employees e ON e.id=u.employee_id ORDER BY u.created_at DESC"
                )
                rows = cur.fetchall()
        except Error as e:
            app.logger.error(f"Users list error: {e}")
        finally:
            conn.close()
    return render_template("admin/users_list.html", users=rows)


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_users_edit(user_id):
    conn = get_db_connection()
    user = None
    employees = []
    if request.method == "POST":
        role = request.form.get("role", "user")
        is_active = 1 if request.form.get("is_active") == "on" else 0
        emp_raw = request.form.get("employee_id")
        employee_id = int(emp_raw) if emp_raw and emp_raw.isdigit() else None
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET role=%s, is_active=%s, employee_id=%s, updated_at=%s WHERE id=%s",
                        (role, is_active, employee_id, datetime.utcnow(), user_id),
                    )
                    conn.commit()
                flash("User updated.", "success")
                return redirect(url_for("admin_users_list"))
            except Error as e:
                app.logger.error(f"User update error: {e}")
                flash("Error updating user.", "danger")
            finally:
                conn.close()
        return redirect(url_for("admin_users_list"))
    # GET
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT id, username, role, is_active, employee_id FROM users WHERE id=%s", (user_id,))
                user = cur.fetchone()
                cur.execute("SELECT id, name FROM employees WHERE is_active=1 ORDER BY name ASC")
                employees = cur.fetchall()
        except Error as e:
            app.logger.error(f"User fetch error: {e}")
        finally:
            conn.close()
    if not user:
        flash("User not found.", "warning")
        return redirect(url_for("admin_users_list"))
    return render_template("admin/user_form.html", user=user, employees=employees)


# ---------------------- Admin Auth ----------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    # Backward compatibility: redirect to unified signin with admin preselected
    next_url = request.args.get("next")
    return redirect(url_for("signin", next=next_url))


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    try:
        log_auth_event("logout", username="admin", user_id=None, is_admin=True)
    except Exception:
        pass
    flash("Logged out.", "info")
    return redirect(url_for("admin_login"))


# ---------------------- Admin Dashboard ----------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = {"contacts": 0, "services": 0, "employees": 0, "tasks": 0, "actions": 0}
    latest_contacts = []
    latest_actions = []
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT COUNT(*) AS c FROM contacts")
                stats["contacts"] = (cur.fetchone() or {}).get("c", 0)
                cur.execute("SELECT COUNT(*) AS c FROM services")
                stats["services"] = (cur.fetchone() or {}).get("c", 0)
                cur.execute("SELECT COUNT(*) AS c FROM employees")
                stats["employees"] = (cur.fetchone() or {}).get("c", 0)
                cur.execute("SELECT COUNT(*) AS c FROM tasks")
                stats["tasks"] = (cur.fetchone() or {}).get("c", 0)
                cur.execute(
                    "SELECT id, name, email, message, created_at FROM contacts ORDER BY created_at DESC LIMIT 5"
                )
                latest_contacts = cur.fetchall()
                # Admin actions summary and latest
                ensure_admin_actions_table(conn)
                cur.execute("SELECT COUNT(*) AS c FROM admin_actions")
                stats["actions"] = (cur.fetchone() or {}).get("c", 0)
                cur.execute(
                    """
                    SELECT id, actor, tool, action, status, device_id, started_at, ended_at
                    FROM admin_actions
                    ORDER BY started_at DESC
                    LIMIT 5
                    """
                )
                latest_actions = cur.fetchall()
        except Error as e:
            app.logger.error(f"Dashboard query error: {e}")
        finally:
            conn.close()
    return render_template("admin/dashboard.html", stats=stats, latest_contacts=latest_contacts, latest_actions=latest_actions)


# ---------------------- Admin: Auth Activity Monitoring ----------------------
@app.route("/admin/activity")
@admin_required
def admin_activity():
    """Show recent authentication and access activity."""
    rows = []
    summary = {"logins": 0, "failures": 0, "logouts": 0}
    device_filter = (request.args.get("device") or "").lower()
    if device_filter not in ("mobile", "desktop", ""):
        device_filter = ""
    conn = get_db_connection()
    if conn:
        ensure_auth_logs_table(conn)
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT id, username, user_id, is_admin, action, ip, user_agent, device_type, at
                    FROM auth_logs
                    ORDER BY at DESC
                    LIMIT 200
                    """
                )
                rows = cur.fetchall() or []
                if device_filter:
                    filtered = []
                    for r in rows:
                        ua = r.get("user_agent") if isinstance(r, dict) else None
                        dt = r.get("device_type") if isinstance(r, dict) else None
                        dt = (dt or _detect_device_type(ua)).lower()
                        if dt == device_filter:
                            filtered.append(r)
                    rows = filtered
                # summary counts (last 7 days)
                cur.execute(
                    """
                    SELECT action, COUNT(*) c FROM auth_logs
                    WHERE at >= %s
                    GROUP BY action
                    """,
                    (datetime.utcnow() - timedelta(days=7),),
                )
                for r in cur.fetchall():
                    if r["action"] == "login_success":
                        summary["logins"] = int(r["c"]) or 0
                    elif r["action"] == "login_failure":
                        summary["failures"] = int(r["c"]) or 0
                    elif r["action"] == "logout":
                        summary["logouts"] = int(r["c"]) or 0
        except Error as e:
            app.logger.error(f"admin_activity query error: {e}")
        finally:
            conn.close()
    return render_template("admin/activity_logs.html", rows=rows, summary=summary, device_filter=device_filter)


# ---------------------- Admin: Remote Management Actions ----------------------
def ensure_admin_actions_table(conn):
    """Create admin_actions table if it does not exist."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_actions (
                  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                  actor VARCHAR(100) NULL,
                  target_user_id INT UNSIGNED NULL,
                  device_id VARCHAR(100) NULL,
                  tool ENUM('AnyDesk','RDP','VNC','MDM','Other') NOT NULL DEFAULT 'Other',
                  action VARCHAR(100) NOT NULL,
                  status ENUM('initiated','in_progress','completed','failed') NOT NULL DEFAULT 'initiated',
                  notes TEXT NULL,
                  metadata TEXT NULL,
                  started_at DATETIME NOT NULL,
                  ended_at DATETIME NULL,
                  PRIMARY KEY (id),
                  INDEX (target_user_id),
                  INDEX (tool),
                  INDEX (status),
                  INDEX (started_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        conn.commit()
    except Error as e:
        app.logger.error(f"ensure_admin_actions_table error: {e}")


def log_admin_action(actor: str, action: str, tool: str = 'Other', target_user_id: int = None, device_id: str = None, status: str = 'initiated', notes: str = None, metadata: str = None, ended: bool = False):
    conn = get_db_connection()
    if not conn:
        return
    ensure_admin_actions_table(conn)
    try:
        with conn.cursor() as cur:
            if ended:
                cur.execute(
                    """
                    INSERT INTO admin_actions (actor, target_user_id, device_id, tool, action, status, notes, metadata, started_at, ended_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (actor, target_user_id, device_id, tool, action, status, notes, metadata, datetime.utcnow(), datetime.utcnow()),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO admin_actions (actor, target_user_id, device_id, tool, action, status, notes, metadata, started_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (actor, target_user_id, device_id, tool, action, status, notes, metadata, datetime.utcnow()),
                )
            conn.commit()
    except Error as e:
        app.logger.error(f"log_admin_action error: {e}")
    finally:
        conn.close()


@app.route('/admin/actions')
@admin_required
def admin_actions_list():
    rows = []
    conn = get_db_connection()
    if conn:
        ensure_admin_actions_table(conn)
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT id, actor, target_user_id, device_id, tool, action, status, started_at, ended_at
                    FROM admin_actions
                    ORDER BY started_at DESC
                    LIMIT 200
                    """
                )
                rows = cur.fetchall()
        except Error as e:
            app.logger.error(f"admin_actions_list error: {e}")
        finally:
            conn.close()
    return render_template('admin/actions_list.html', actions=rows)


@app.route('/admin/actions/new', methods=['GET','POST'])
@admin_required
def admin_actions_new():
    if request.method == 'POST':
        tool = (request.form.get('tool') or 'Other')
        action_name = (request.form.get('action') or '').strip() or 'remote_action'
        target_user_id = request.form.get('target_user_id')
        target_user_id = int(target_user_id) if target_user_id and target_user_id.isdigit() else None
        device_id = (request.form.get('device_id') or '').strip() or None
        notes = (request.form.get('notes') or '').strip() or None
        log_admin_action(actor='admin', action=action_name, tool=tool, target_user_id=target_user_id, device_id=device_id, status='initiated', notes=notes)
        flash('Admin action logged.', 'success')
        return redirect(url_for('admin_actions_list'))
    return render_template('admin/action_form.html')


@app.route('/admin/actions/<int:action_id>/complete', methods=['POST'])
@admin_required
def admin_actions_complete(action_id):
    conn = get_db_connection()
    if conn:
        ensure_admin_actions_table(conn)
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE admin_actions SET status=%s, ended_at=%s WHERE id=%s", ('completed', datetime.utcnow(), action_id))
                conn.commit()
            flash('Action marked as completed.', 'success')
        except Error as e:
            app.logger.error(f"admin_actions_complete error: {e}")
            flash('Could not update action.', 'danger')
        finally:
            conn.close()
    return redirect(url_for('admin_actions_list'))


@app.route('/hooks/mdm', methods=['POST'])
def mdm_webhook():
    """Optional: receive events from an external MDM/remote tool.
    Protect with a shared token in .env: MDM_WEBHOOK_TOKEN
    Body JSON example:
    {"action":"remote_session","tool":"AnyDesk","target_user_id":1,"device_id":"PC-123","status":"completed","notes":"duration 10m"}
    """
    load_dotenv(override=True)
    expected = os.getenv('MDM_WEBHOOK_TOKEN')
    provided = request.headers.get('X-Auth-Token') or request.args.get('token')
    if not expected or provided != expected:
        return jsonify({"error":"unauthorized"}), 401
    try:
        data = request.get_json(force=True) or {}
        action_name = (data.get('action') or 'remote_action')
        tool = (data.get('tool') or 'MDM')
        target_user_id = data.get('target_user_id')
        target_user_id = int(target_user_id) if isinstance(target_user_id, (int, str)) and str(target_user_id).isdigit() else None
        device_id = data.get('device_id')
        status = (data.get('status') or 'in_progress')
        notes = data.get('notes')
        metadata = data.get('metadata')
        if isinstance(metadata, (dict, list)):
            import json as _json
            metadata = _json.dumps(metadata)
        log_admin_action(actor='mdm', action=action_name, tool=tool, target_user_id=target_user_id, device_id=device_id, status=status, notes=notes, metadata=metadata, ended=(status in ('completed','failed')))
        return jsonify({"ok":True})
    except Exception as e:
        app.logger.error(f"mdm_webhook error: {e}")
        return jsonify({"error":"bad_request"}), 400


# ---------------------- Admin Services CRUD ----------------------
@app.route("/admin/services")
@admin_required
def admin_services_list():
    conn = get_db_connection()
    services = []
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT id, title, description, is_active, created_at, updated_at FROM services ORDER BY created_at DESC")
                services = cur.fetchall()
        except Error as e:
            app.logger.error(f"Admin services list error: {e}")
        finally:
            conn.close()
    return render_template("admin/services_list.html", services=services)


@app.route("/admin/services/new", methods=["GET", "POST"])
@admin_required
def admin_services_new():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        is_active = 1 if request.form.get("is_active") == "on" else 0
        featured = 1 if request.form.get("featured") == "on" else 0
        sort_order = int(request.form.get("sort_order", "0") or 0)
        image_filename = None
        file = request.files.get("image")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid image type. Allowed: png, jpg, jpeg, gif, webp", "danger")
                return redirect(url_for("admin_services_new"))
            safe_name = secure_filename(file.filename)
            # ensure unique filename
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            name, ext = os.path.splitext(safe_name)
            image_filename = f"{name}-{timestamp}{ext}"
            save_path = os.path.join(app.static_folder, UPLOAD_SUBDIR, image_filename)
            file.save(save_path)
        if not title:
            flash("Title is required.", "danger")
            return redirect(url_for("admin_services_new"))
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO services (title, description, is_active, featured, sort_order, image_filename, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            title,
                            description,
                            is_active,
                            featured,
                            sort_order,
                            image_filename,
                            datetime.utcnow(),
                            datetime.utcnow(),
                        ),
                    )
                    conn.commit()
                flash("Service created.", "success")
                return redirect(url_for("admin_services_list"))
            except Error as e:
                app.logger.error(f"Service create error: {e}")
                flash("Error creating service.", "danger")
            finally:
                conn.close()
    return render_template("admin/service_form.html", mode="new", service=None)


@app.route("/admin/services/<int:service_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_services_edit(service_id):
    conn = get_db_connection()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        is_active = 1 if request.form.get("is_active") == "on" else 0
        featured = 1 if request.form.get("featured") == "on" else 0
        sort_order = int(request.form.get("sort_order", "0") or 0)
        image_filename = None
        file = request.files.get("image")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid image type. Allowed: png, jpg, jpeg, gif, webp", "danger")
                return redirect(url_for("admin_services_edit", service_id=service_id))
            safe_name = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            name, ext = os.path.splitext(safe_name)
            image_filename = f"{name}-{timestamp}{ext}"
            save_path = os.path.join(app.static_folder, UPLOAD_SUBDIR, image_filename)
            file.save(save_path)
        if not title:
            flash("Title is required.", "danger")
            return redirect(url_for("admin_services_edit", service_id=service_id))
        if conn:
            try:
                with conn.cursor() as cur:
                    if image_filename:
                        cur.execute(
                            "UPDATE services SET title=%s, description=%s, is_active=%s, featured=%s, sort_order=%s, image_filename=%s, updated_at=%s WHERE id=%s",
                            (title, description, is_active, featured, sort_order, image_filename, datetime.utcnow(), service_id),
                        )
                    else:
                        cur.execute(
                            "UPDATE services SET title=%s, description=%s, is_active=%s, featured=%s, sort_order=%s, updated_at=%s WHERE id=%s",
                            (title, description, is_active, featured, sort_order, datetime.utcnow(), service_id),
                        )
                    conn.commit()
                flash("Service updated.", "success")
                return redirect(url_for("admin_services_list"))
            except Error as e:
                app.logger.error(f"Service update error: {e}")
                flash("Error updating service.", "danger")
            finally:
                conn.close()
        return redirect(url_for("admin_services_list"))
    # GET load service
    service = None
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT id, title, description, is_active, featured, sort_order, image_filename FROM services WHERE id=%s", (service_id,))
                service = cur.fetchone()
        except Error as e:
            app.logger.error(f"Service fetch error: {e}")
        finally:
            conn.close()
    if not service:
        flash("Service not found.", "warning")
        return redirect(url_for("admin_services_list"))
    return render_template("admin/service_form.html", mode="edit", service=service)


# ---------------------- Admin Employees CRUD ----------------------

@app.route("/admin/employees")
@admin_required
def admin_employees_list():
    conn = get_db_connection()
    rows = []
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    "SELECT id, name, position, is_active, sort_order, created_at, updated_at FROM employees ORDER BY sort_order ASC, created_at DESC"
                )
                rows = cur.fetchall()
        except Error as e:
            app.logger.error(f"Employees list error: {e}")
        finally:
            conn.close()
    return render_template("admin/employees_list.html", employees=rows)


@app.route("/admin/employees/new", methods=["GET", "POST"])
@admin_required
def admin_employees_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        position = request.form.get("position", "").strip()
        is_active = 1 if request.form.get("is_active") == "on" else 0
        sort_order = int(request.form.get("sort_order", "0") or 0)
        photo_filename = None
        file = request.files.get("photo")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid image type. Allowed: png, jpg, jpeg, gif, webp", "danger")
                return redirect(url_for("admin_employees_new"))
            safe_name = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            name_noext, ext = os.path.splitext(safe_name)
            photo_filename = f"{name_noext}-{timestamp}{ext}"
            file.save(os.path.join(app.static_folder, UPLOAD_SUBDIR, photo_filename))
        if not name or not position:
            flash("Name and position are required.", "danger")
            return redirect(url_for("admin_employees_new"))
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO employees (name, position, photo_filename, is_active, sort_order, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (name, position, photo_filename, is_active, sort_order, datetime.utcnow(), datetime.utcnow()),
                    )
                    conn.commit()
                flash("Employee created.", "success")
                return redirect(url_for("admin_employees_list"))
            except Error as e:
                app.logger.error(f"Employee create error: {e}")
                flash("Error creating employee.", "danger")
            finally:
                conn.close()
    return render_template("admin/employee_form.html", mode="new", employee=None)


@app.route("/admin/employees/<int:emp_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_employees_edit(emp_id):
    conn = get_db_connection()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        position = request.form.get("position", "").strip()
        is_active = 1 if request.form.get("is_active") == "on" else 0
        sort_order = int(request.form.get("sort_order", "0") or 0)
        photo_filename = None
        file = request.files.get("photo")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid image type. Allowed: png, jpg, jpeg, gif, webp", "danger")
                return redirect(url_for("admin_employees_edit", emp_id=emp_id))
            safe_name = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            name_noext, ext = os.path.splitext(safe_name)
            photo_filename = f"{name_noext}-{timestamp}{ext}"
            file.save(os.path.join(app.static_folder, UPLOAD_SUBDIR, photo_filename))
        if not name or not position:
            flash("Name and position are required.", "danger")
            return redirect(url_for("admin_employees_edit", emp_id=emp_id))
        if conn:
            try:
                with conn.cursor() as cur:
                    if photo_filename:
                        cur.execute(
                            "UPDATE employees SET name=%s, position=%s, photo_filename=%s, is_active=%s, sort_order=%s, updated_at=%s WHERE id=%s",
                            (name, position, photo_filename, is_active, sort_order, datetime.utcnow(), emp_id),
                        )
                    else:
                        cur.execute(
                            "UPDATE employees SET name=%s, position=%s, is_active=%s, sort_order=%s, updated_at=%s WHERE id=%s",
                            (name, position, is_active, sort_order, datetime.utcnow(), emp_id),
                        )
                    conn.commit()
                flash("Employee updated.", "success")
                return redirect(url_for("admin_employees_list"))
            except Error as e:
                app.logger.error(f"Employee update error: {e}")
                flash("Error updating employee.", "danger")
            finally:
                conn.close()
        return redirect(url_for("admin_employees_list"))
    # GET
    employee = None
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    "SELECT id, name, position, photo_filename, is_active, sort_order FROM employees WHERE id=%s",
                    (emp_id,),
                )
                employee = cur.fetchone()
        except Error as e:
            app.logger.error(f"Employee fetch error: {e}")
        finally:
            conn.close()
    if not employee:
        flash("Employee not found.", "warning")
        return redirect(url_for("admin_employees_list"))
    return render_template("admin/employee_form.html", mode="edit", employee=employee)


@app.route("/admin/employees/<int:emp_id>/delete", methods=["POST"])
@admin_required
def admin_employees_delete(emp_id):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employees WHERE id=%s", (emp_id,))
                conn.commit()
            flash("Employee deleted.", "info")
        except Error as e:
            app.logger.error(f"Employee delete error: {e}")
            flash("Error deleting employee.", "danger")
        finally:
            conn.close()
    return redirect(url_for("admin_employees_list"))

@app.route("/admin/services/<int:service_id>/delete", methods=["POST"]) 
@admin_required
def admin_services_delete(service_id):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM services WHERE id=%s", (service_id,))
                conn.commit()
            flash("Service deleted.", "info")
        except Error as e:
            app.logger.error(f"Service delete error: {e}")
            flash("Error deleting service.", "danger")
        finally:
            conn.close()
    return redirect(url_for("admin_services_list"))


# ---------------------- Admin Tasks CRUD ----------------------
@app.route("/admin/tasks")
@admin_required
def admin_tasks_list():
    # Filters
    status = request.args.get("status") or ""
    assignee = request.args.get("assignee") or ""
    where = []
    params = []
    if status in {"todo", "in_progress", "done", "blocked"}:
        where.append("t.status=%s")
        params.append(status)
    if assignee.isdigit():
        where.append("t.employee_id=%s")
        params.append(int(assignee))

    conn = get_db_connection()
    tasks = []
    employees = []
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                base_sql = (
                    """
                    SELECT t.id, t.title, t.description, t.status, t.priority, t.due_date, t.created_at, t.updated_at,
                           t.attachment_filename, t.github_url,
                           e.name AS employee_name, e.id AS employee_id
                    FROM tasks t
                    LEFT JOIN employees e ON e.id = t.employee_id
                    {where_clause}
                    ORDER BY FIELD(t.status,'blocked','in_progress','todo','done'), t.due_date IS NULL, t.due_date ASC, t.created_at DESC
                    """
                )
                where_clause = (" WHERE " + " AND ".join(where)) if where else ""
                cur.execute(base_sql.format(where_clause=where_clause), params)
                tasks = cur.fetchall()
                # Employees for filter dropdown
                cur.execute("SELECT id, name FROM employees WHERE is_active=1 ORDER BY name ASC")
                employees = cur.fetchall()
        except Error as e:
            app.logger.error(f"Tasks list error: {e}")
        finally:
            conn.close()
    return render_template("admin/tasks_list.html", tasks=tasks, employees=employees, cur_status=status, cur_assignee=assignee)


@app.route("/admin/tasks/new", methods=["GET", "POST"])
@admin_required
def admin_tasks_new():
    conn = get_db_connection()
    # Fetch employees for assignment dropdown
    employees = []
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT id, name FROM employees WHERE is_active=1 ORDER BY sort_order ASC, name ASC")
                employees = cur.fetchall()
        except Error as e:
            app.logger.error(f"Employees fetch for tasks error: {e}")
        finally:
            conn.close()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        employee_id_raw = request.form.get("employee_id")
        employee_id = int(employee_id_raw) if employee_id_raw else None
        status = request.form.get("status", "todo")
        priority = request.form.get("priority", "medium")
        due_date = request.form.get("due_date") or None
        github_url = (request.form.get("github_url") or "").strip() or None
        # handle attachment image
        attachment_filename = None
        file = request.files.get("attachment")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid attachment type. Allowed: png, jpg, jpeg, gif, webp", "danger")
                return redirect(url_for("admin_tasks_new"))
            safe_name = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            name_noext, ext = os.path.splitext(safe_name)
            attachment_filename = f"{name_noext}-{timestamp}{ext}"
            file.save(os.path.join(app.static_folder, UPLOAD_SUBDIR, attachment_filename))
        if not title:
            flash("Title is required.", "danger")
            return redirect(url_for("admin_tasks_new"))
        conn2 = get_db_connection()
        if conn2:
            try:
                with conn2.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO tasks (title, description, employee_id, status, priority, attachment_filename, github_url, due_date, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            title,
                            description or None,
                            employee_id,
                            status,
                            priority,
                            attachment_filename,
                            github_url,
                            due_date,
                            datetime.utcnow(),
                            datetime.utcnow(),
                        ),
                    )
                    conn2.commit()
                flash("Task created.", "success")
                return redirect(url_for("admin_tasks_list"))
            except Error as e:
                app.logger.error(f"Task create error: {e}")
                flash("Error creating task.", "danger")
            finally:
                conn2.close()
    return render_template("admin/task_form.html", mode="new", task=None, employees=employees)


@app.route("/admin/tasks/<int:task_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_tasks_edit(task_id):
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        employee_id_raw = request.form.get("employee_id")
        employee_id = int(employee_id_raw) if employee_id_raw else None
        status = request.form.get("status", "todo")
        priority = request.form.get("priority", "medium")
        due_date = request.form.get("due_date") or None
        github_url = (request.form.get("github_url") or "").strip() or None
        # optional new attachment
        attachment_filename = None
        file = request.files.get("attachment")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid attachment type. Allowed: png, jpg, jpeg, gif, webp", "danger")
                return redirect(url_for("admin_tasks_edit", task_id=task_id))
            safe_name = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            name_noext, ext = os.path.splitext(safe_name)
            attachment_filename = f"{name_noext}-{timestamp}{ext}"
            file.save(os.path.join(app.static_folder, UPLOAD_SUBDIR, attachment_filename))
        if not title:
            flash("Title is required.", "danger")
            return redirect(url_for("admin_tasks_edit", task_id=task_id))
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    if attachment_filename is not None:
                        cur.execute(
                            """
                            UPDATE tasks
                            SET title=%s, description=%s, employee_id=%s, status=%s, priority=%s, attachment_filename=%s, github_url=%s, due_date=%s, updated_at=%s
                            WHERE id=%s
                            """,
                            (title, description or None, employee_id, status, priority, attachment_filename, github_url, due_date, datetime.utcnow(), task_id),
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE tasks
                            SET title=%s, description=%s, employee_id=%s, status=%s, priority=%s, github_url=%s, due_date=%s, updated_at=%s
                            WHERE id=%s
                            """,
                            (title, description or None, employee_id, status, priority, github_url, due_date, datetime.utcnow(), task_id),
                        )
                    conn.commit()
                flash("Task updated.", "success")
                return redirect(url_for("admin_tasks_list"))
            except Error as e:
                app.logger.error(f"Task update error: {e}")
                flash("Error updating task.", "danger")
            finally:
                conn.close()
        return redirect(url_for("admin_tasks_list"))
    # GET load task and employees
    conn = get_db_connection()
    task = None
    employees = []
    if conn:
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    "SELECT id, title, description, employee_id, status, priority, attachment_filename, github_url, due_date FROM tasks WHERE id=%s",
                    (task_id,),
                )
                task = cur.fetchone()
                cur.execute("SELECT id, name FROM employees WHERE is_active=1 ORDER BY sort_order ASC, name ASC")
                employees = cur.fetchall()
        except Error as e:
            app.logger.error(f"Task fetch error: {e}")
        finally:
            conn.close()
    if not task:
        flash("Task not found.", "warning")
        return redirect(url_for("admin_tasks_list"))
    return render_template("admin/task_form.html", mode="edit", task=task, employees=employees)


@app.route("/admin/tasks/<int:task_id>/delete", methods=["POST"])
@admin_required
def admin_tasks_delete(task_id):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
                conn.commit()
            flash("Task deleted.", "info")
        except Error as e:
            app.logger.error(f"Task delete error: {e}")
            flash("Error deleting task.", "danger")
        finally:
            conn.close()
    return redirect(url_for("admin_tasks_list"))


# ---------------------- Admin Messaging ----------------------
@app.route("/admin/messages", methods=["GET", "POST"])
@admin_required
def admin_messages():
    wa_url = None
    if request.method == "POST":
        # Common attachment handling
        attachment_filename = None
        attachment_path = None
        attachment_url = None
        file = request.files.get("attachment")
        if file and file.filename:
            if not allowed_attachment(file.filename):
                flash("Invalid attachment type.", "danger")
                return render_template("admin/message_form.html", wa_url=None)
            safe_name = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            name_noext, ext = os.path.splitext(safe_name)
            attachment_filename = f"{name_noext}-{timestamp}{ext}"
            attachment_path = os.path.join(app.static_folder, UPLOAD_SUBDIR, attachment_filename)
            file.save(attachment_path)
            try:
                # absolute URL for WhatsApp sharing
                attachment_url = url_for('static', filename=f"{UPLOAD_SUBDIR}/{attachment_filename}", _external=True)
            except Exception:
                attachment_url = None

        # Send Email via SMTP if selected
        if request.form.get("send_email") == "on":
            to_email = (request.form.get("to_email") or "").strip()
            subject = (request.form.get("subject") or "").strip() or "(no subject)"
            body = (request.form.get("body") or "").strip()
            if not to_email:
                flash("Recipient email is required to send.", "danger")
            else:
                smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
                smtp_port = int(os.getenv("SMTP_PORT", "587"))
                smtp_user = os.getenv("SMTP_USER", "")
                smtp_pass = os.getenv("SMTP_PASS", "")
                smtp_use_tls = (os.getenv("SMTP_USE_TLS", "true").lower() != "false")
                email_from = os.getenv("EMAIL_FROM", smtp_user or "no-reply@example.com")

                msg = EmailMessage()
                msg["From"] = email_from
                msg["To"] = to_email
                msg["Subject"] = subject
                msg.set_content(body or "")
                # Attachment
                if attachment_path and os.path.exists(attachment_path):
                    ctype, encoding = mimetypes.guess_type(attachment_path)
                    if ctype is None:
                        ctype = "application/octet-stream"
                    maintype, subtype = ctype.split("/", 1)
                    with open(attachment_path, "rb") as f:
                        msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=attachment_filename)
                try:
                    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                        if smtp_use_tls:
                            server.starttls()
                        if smtp_user and smtp_pass:
                            server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                    flash("Email sent successfully.", "success")
                except Exception as e:
                    app.logger.error(f"SMTP send error: {e}")
                    flash("Failed to send email. Check SMTP settings.", "danger")

        # Build WhatsApp link if selected
        if request.form.get("make_whatsapp") == "on":
            phone = (request.form.get("wa_phone") or "").strip()
            wa_text = (request.form.get("wa_text") or "").strip()
            if attachment_url:
                wa_text = f"{wa_text}\nAttachment: {attachment_url}".strip()
            # Normalize phone: remove non-digits
            phone_digits = ''.join(ch for ch in phone if ch.isdigit())
            if not phone_digits:
                flash("Phone number required for WhatsApp link.", "danger")
            else:
                wa_url = f"https://wa.me/{phone_digits}?text={quote_plus(wa_text)}"
                flash("WhatsApp link generated below.", "info")

    return render_template("admin/message_form.html", wa_url=wa_url)


# ---------------------- Admin Settings: Email (Gmail SMTP) ----------------------
@app.route("/admin/settings/email", methods=["GET", "POST"])
@admin_required
def admin_email_settings():
    # Determine .env path relative to this file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base_dir, ".env")

    def read_env_lines(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    def write_env_lines(path, lines):
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # Keys we manage from UI
    managed_keys = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASS",
        "SMTP_USE_TLS",
        "EMAIL_FROM",
    ]

    if request.method == "POST":
        # Collect submitted values
        new_values = {
            "SMTP_HOST": (request.form.get("SMTP_HOST") or "smtp.gmail.com").strip(),
            "SMTP_PORT": (request.form.get("SMTP_PORT") or "587").strip(),
            "SMTP_USER": (request.form.get("SMTP_USER") or "").strip(),
            "SMTP_PASS": (request.form.get("SMTP_PASS") or "").strip(),
            "SMTP_USE_TLS": "true" if (request.form.get("SMTP_USE_TLS") == "on") else "false",
            "EMAIL_FROM": (request.form.get("EMAIL_FROM") or "").strip(),
        }

        # Read current .env, update or append managed keys
        lines = read_env_lines(env_path)
        updated = set()
        out_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                out_lines.append(line)
                continue
            key, _, _ = stripped.partition("=")
            if key in managed_keys:
                out_lines.append(f"{key}={new_values[key]}")
                updated.add(key)
            else:
                out_lines.append(line)
        # Append any new keys not present
        for k in managed_keys:
            if k not in updated:
                out_lines.append(f"{k}={new_values[k]}")

        write_env_lines(env_path, out_lines)
        # Reload environment for this process
        try:
            load_dotenv(dotenv_path=env_path, override=True)
        except Exception:
            pass
        flash("SMTP settings saved.", "success")
        return redirect(url_for("admin_email_settings"))

    # GET: load current values from env (after load_dotenv at startup)
    current = {
        "SMTP_HOST": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "SMTP_PORT": os.getenv("SMTP_PORT", "587"),
        "SMTP_USER": os.getenv("SMTP_USER", ""),
        # Do not expose real password; just indicate if set
        "SMTP_PASS_SET": bool(os.getenv("SMTP_PASS", "")),
        "SMTP_USE_TLS": os.getenv("SMTP_USE_TLS", "true"),
        "EMAIL_FROM": os.getenv("EMAIL_FROM", os.getenv("SMTP_USER", "")),
    }
    return render_template("admin/email_settings.html", current=current)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
