-- Create database (run if not existing)
CREATE DATABASE IF NOT EXISTS company_site DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE company_site;

-- Contacts table
CREATE TABLE IF NOT EXISTS contacts (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(120) NOT NULL,
  email VARCHAR(190) NOT NULL,
  message TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  INDEX (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Employees table
CREATE TABLE IF NOT EXISTS employees (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(150) NOT NULL,
  position VARCHAR(150) NOT NULL,
  photo_filename VARCHAR(255) NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  INDEX (is_active),
  INDEX (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Users table (for application logins)
CREATE TABLE IF NOT EXISTS users (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','editor','employee','user') NOT NULL DEFAULT 'user',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  employee_id INT UNSIGNED NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  INDEX (employee_id),
  CONSTRAINT fk_users_employee
    FOREIGN KEY (employee_id)
    REFERENCES employees(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Services table
CREATE TABLE IF NOT EXISTS services (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  title VARCHAR(150) NOT NULL,
  description TEXT NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  featured TINYINT(1) NOT NULL DEFAULT 0,
  sort_order INT NOT NULL DEFAULT 0,
  image_filename VARCHAR(255) NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  INDEX (is_active),
  INDEX (featured),
  INDEX (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  title VARCHAR(200) NOT NULL,
  description TEXT NULL,
  employee_id INT UNSIGNED NULL,
  status ENUM('todo','in_progress','done','blocked') NOT NULL DEFAULT 'todo',
  priority ENUM('low','medium','high') NOT NULL DEFAULT 'medium',
  attachment_filename VARCHAR(255) NULL,
  github_url VARCHAR(255) NULL,
  due_date DATE NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  INDEX (employee_id),
  INDEX (status),
  INDEX (priority),
  CONSTRAINT fk_tasks_employee
    FOREIGN KEY (employee_id)
    REFERENCES employees(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
