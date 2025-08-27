import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error
from werkzeug.utils import secure_filename

# Load environment variables from .env if present
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change")

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
UPLOAD_SUBDIR = "uploads"
os.makedirs(os.path.join(app.static_folder, UPLOAD_SUBDIR), exist_ok=True)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        app.logger.error(f"MySQL connection error: {e}")
        return None


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please log in to access admin.", "warning")
            return redirect(url_for("admin_login", next=request.path))
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


# ---------------------- Admin Auth ----------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        # Reload .env each login attempt to reflect recent changes without restart
        load_dotenv(override=True)
        env_user = os.getenv("ADMIN_USERNAME", "admin")
        env_pass = os.getenv("ADMIN_PASSWORD", "admin")
        if username == env_user and password == env_pass:
            session["admin_logged_in"] = True
            flash("Logged in successfully.", "success")
            next_url = request.args.get("next") or url_for("admin_dashboard")
            return redirect(next_url)
        flash("Invalid credentials.", "danger")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("admin_login"))


# ---------------------- Admin Dashboard ----------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = {"contacts": 0, "services": 0, "employees": 0}
    latest_contacts = []
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
                cur.execute(
                    "SELECT id, name, email, message, created_at FROM contacts ORDER BY created_at DESC LIMIT 5"
                )
                latest_contacts = cur.fetchall()
        except Error as e:
            app.logger.error(f"Dashboard query error: {e}")
        finally:
            conn.close()
    return render_template("admin/dashboard.html", stats=stats, latest_contacts=latest_contacts)


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
