<<<<<<< HEAD
# Company Profile Website (Flask + MySQL)

A minimal company profile site using Flask, Bootstrap 5, and MySQL with a working contact form.

## Features
- Home, About, Services, Contact pages
- Bootstrap 5 responsive UI
- Contact form persists to MySQL (`contacts` table)
- Environment-based configuration with `python-dotenv`

## Requirements
- Python 3.10+
- MySQL server (e.g., via WAMP/XAMPP or standalone)

## Setup
1. Clone or open this folder: `c:\\wamp64\\www\\vk\\`
2. Create a virtual environment and activate it:
   - Windows PowerShell:
     ```powershell
     python -m venv .venv
     .venv\\Scripts\\Activate.ps1
     ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Create a `.env` file based on `.env.example` and set your MySQL credentials.
5. Initialize the database:
   - Option A: MySQL shell / client
     ```sql
     SOURCE c:/wamp64/www/vk/schema.sql;
     ```
   - Option B: Copy the SQL statements and run them in your MySQL client (phpMyAdmin/MySQL Workbench).

## Run
```powershell
$env:FLASK_APP="app.py"
python app.py
```
App will start on http://127.0.0.1:5000 by default.

## Notes
- If connecting to MySQL on WAMP, default user is often `root` with empty password.
- Update `.env` if your host/port or credentials differ.
- For production, set a strong `FLASK_SECRET_KEY` and disable `debug=True`.

## Admin
- Routes:
  - Login: `/admin/login`
  - Dashboard: `/admin`
  - Services CRUD: `/admin/services`, `/admin/services/new`, `/admin/services/<id>/edit`
- Default credentials (override in `.env`):
  - `ADMIN_USERNAME=admin`
  - `ADMIN_PASSWORD=admin`

### Initialize Services table
Run the updated schema to create the `services` table:

```sql
SOURCE c:/wamp64/www/vk/schema.sql;
```

### Manage Services
After logging in, go to Admin -> Services to create, edit, or delete services. Public page `/services` shows only active services.
=======
# vkitnet
>>>>>>> 8c24877d4f2fba6c275ed50d775c2c478f92b598
