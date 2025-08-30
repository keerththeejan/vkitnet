-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1:3306
-- Generation Time: Aug 30, 2025 at 02:28 PM
-- Server version: 8.3.0
-- PHP Version: 8.3.6

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `company_site`
--

-- --------------------------------------------------------

--
-- Table structure for table `admin_actions`
--

DROP TABLE IF EXISTS `admin_actions`;
CREATE TABLE IF NOT EXISTS `admin_actions` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `target_user_id` int UNSIGNED DEFAULT NULL,
  `device_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `tool` enum('AnyDesk','RDP','VNC','MDM','Other') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Other',
  `action` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('initiated','in_progress','completed','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'initiated',
  `notes` text COLLATE utf8mb4_unicode_ci,
  `metadata` text COLLATE utf8mb4_unicode_ci,
  `started_at` datetime NOT NULL,
  `ended_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `target_user_id` (`target_user_id`),
  KEY `tool` (`tool`),
  KEY `status` (`status`),
  KEY `started_at` (`started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `auth_logs`
--

DROP TABLE IF EXISTS `auth_logs`;
CREATE TABLE IF NOT EXISTS `auth_logs` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
  `username` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_id` int UNSIGNED DEFAULT NULL,
  `is_admin` tinyint(1) NOT NULL DEFAULT '0',
  `action` enum('login_success','login_failure','logout') COLLATE utf8mb4_unicode_ci NOT NULL,
  `ip` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_agent` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `device_type` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `username` (`username`),
  KEY `user_id` (`user_id`),
  KEY `is_admin` (`is_admin`),
  KEY `action` (`action`),
  KEY `at` (`at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `contacts`
--

DROP TABLE IF EXISTS `contacts`;
CREATE TABLE IF NOT EXISTS `contacts` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(190) COLLATE utf8mb4_unicode_ci NOT NULL,
  `message` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `contacts`
--

INSERT INTO `contacts` (`id`, `name`, `email`, `message`, `created_at`) VALUES
(1, 'Maya', 'maya@example.com', 'We need a small CRM for our sales team.', '2025-08-29 21:34:34'),
(2, 'Jamal', 'jamal@example.com', 'Requesting a site audit and optimization.', '2025-08-29 21:34:34'),
(3, 'Priya', 'priya@example.com', 'Looking for a CCTV deployment quote.', '2025-08-29 21:34:34');

-- --------------------------------------------------------

--
-- Table structure for table `employees`
--

DROP TABLE IF EXISTS `employees`;
CREATE TABLE IF NOT EXISTS `employees` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `position` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `photo_filename` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `sort_order` int NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `is_active` (`is_active`),
  KEY `sort_order` (`sort_order`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `employees`
--

INSERT INTO `employees` (`id`, `name`, `position`, `photo_filename`, `is_active`, `sort_order`, `created_at`, `updated_at`) VALUES
(1, 'VIJAY KEERTHTHEEJAN', 'Network Engineer', 'DSC05889-20250827152836424878.jpg', 1, 1, '2025-08-27 20:13:09', '2025-08-27 15:28:36'),
(2, 'Priya Shah', 'Software Developer', NULL, 1, 2, '2025-08-27 20:13:09', '2025-08-27 20:13:09'),
(3, 'Rahul Menon', 'Hardware Specialist', NULL, 1, 3, '2025-08-27 20:13:09', '2025-08-27 20:13:09'),
(4, 'Keerth Theejan', 'Full-Stack Developer', NULL, 1, 1, '2025-08-29 21:34:34', '2025-08-29 21:34:34'),
(5, 'Anya N.', 'Network Engineer', NULL, 1, 2, '2025-08-29 21:34:34', '2025-08-29 21:34:34'),
(6, 'Ravi P.', 'Hardware Technician', NULL, 1, 3, '2025-08-29 21:34:34', '2025-08-29 21:34:34');

-- --------------------------------------------------------

--
-- Table structure for table `services`
--

DROP TABLE IF EXISTS `services`;
CREATE TABLE IF NOT EXISTS `services` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
  `title` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  `featured` tinyint(1) NOT NULL DEFAULT '0',
  `sort_order` int NOT NULL DEFAULT '0',
  `image_filename` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `is_active` (`is_active`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `services`
--

INSERT INTO `services` (`id`, `title`, `description`, `is_active`, `created_at`, `updated_at`, `featured`, `sort_order`, `image_filename`) VALUES
(2, 'SoftWare', 'hi keerththi', 1, '2025-08-27 14:22:13', '2025-08-27 14:33:47', 0, 0, '5309ddf0-67b9-418d-9b57-d937e7a3bfab-20250827142212459328.png'),
(3, 'CCTV Solutions', 'Surveillance design, installation, and remote monitoring for homes and businesses.', 1, '2025-08-27 19:59:32', '2025-08-27 14:33:34', 1, 1, 'cctv.svg'),
(4, 'Logo Design', 'Professional branding, vector assets, and style guides tailored to your identity.', 1, '2025-08-27 19:59:32', '2025-08-27 14:33:42', 0, 2, 'logo-design.svg'),
(5, 'Video Editing', 'Promotional videos, reels, and product demos with motion graphics and sound design.', 1, '2025-08-27 19:59:32', '2025-08-27 19:59:32', 0, 3, 'video-editing.svg'),
(6, 'Final Project Support', 'Academic project guidance, code reviews, documentation, and hardware kits.', 1, '2025-08-27 19:59:32', '2025-08-27 19:59:32', 0, 4, 'final-project.svg'),
(7, 'Modern Software', 'Web apps, internal tools, automation, and integrations built with best practices.', 1, '2025-08-29 21:34:34', '2025-08-29 21:34:34', 1, 1, 'service-placeholder.svg'),
(8, 'Network & Security', 'Design, deployment, and monitoring of robust, secure networks.', 1, '2025-08-29 21:34:34', '2025-08-29 21:34:34', 1, 2, 'cctv.svg'),
(9, 'Hardware Supply', 'Quality hardware procurement with warranty and after‑sales support.', 1, '2025-08-29 21:34:34', '2025-08-29 21:34:34', 1, 3, 'service-placeholder.svg'),
(10, 'CCTV Solutions', 'Surveillance design, installation, and remote monitoring.', 1, '2025-08-29 21:34:34', '2025-08-29 21:34:34', 0, 4, 'cctv.svg'),
(11, 'Logo Design', 'Brand identity, vector assets, and style guides.', 1, '2025-08-29 21:34:34', '2025-08-29 21:34:34', 0, 5, 'service-placeholder.svg'),
(12, 'Video Editing', 'Promos, reels, and product demos with motion graphics.', 1, '2025-08-29 21:34:34', '2025-08-29 21:34:34', 0, 6, 'service-placeholder.svg'),
(13, 'Final Project Support', 'Guidance, code reviews, and hardware kits for academic projects.', 1, '2025-08-29 21:34:34', '2025-08-29 21:34:34', 0, 7, 'service-placeholder.svg');

-- --------------------------------------------------------

--
-- Table structure for table `tasks`
--

DROP TABLE IF EXISTS `tasks`;
CREATE TABLE IF NOT EXISTS `tasks` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `employee_id` int UNSIGNED DEFAULT NULL,
  `status` enum('todo','in_progress','done','blocked') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'todo',
  `priority` enum('low','medium','high') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'medium',
  `due_date` date DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  `attachment_filename` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `github_url` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `employee_id` (`employee_id`),
  KEY `status` (`status`),
  KEY `priority` (`priority`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `tasks`
--

INSERT INTO `tasks` (`id`, `title`, `description`, `employee_id`, `status`, `priority`, `due_date`, `created_at`, `updated_at`, `attachment_filename`, `github_url`) VALUES
(1, 'Build landing page', 'Responsive homepage with services showcase.', 1, 'in_progress', 'high', '2025-09-05', '2025-08-29 21:34:34', '2025-08-29 21:34:34', NULL, NULL),
(2, 'Setup firewall rules', 'Harden perimeter and internal VLANs.', 2, 'todo', 'high', '2025-09-08', '2025-08-29 21:34:34', '2025-08-29 21:34:34', NULL, NULL),
(3, 'Assemble office PCs', 'Prepare 10 workstations with Windows and drivers.', 3, 'todo', 'medium', '2025-09-03', '2025-08-29 21:34:34', '2025-08-29 21:34:34', NULL, NULL),
(4, 'CCTV Deployment - HQ', '16-camera deployment with NVR and remote monitoring.', 2, 'done', 'high', NULL, '2025-08-17 21:42:16', '2025-08-27 21:42:16', 'cctv.svg', NULL),
(5, 'Promo Video Edit', '60-second promo with motion graphics and captions.', 1, 'done', 'medium', NULL, '2025-08-21 21:42:16', '2025-08-28 21:42:16', 'video-editing.svg', NULL),
(6, 'Senior Project Showcase', 'Guided final year project with hardware kit.', 3, 'done', 'medium', NULL, '2025-08-24 21:42:16', '2025-08-29 21:42:16', 'final-project.svg', NULL);

-- --------------------------------------------------------

--
-- Table structure for table `task_time_logs`
--

DROP TABLE IF EXISTS `task_time_logs`;
CREATE TABLE IF NOT EXISTS `task_time_logs` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
  `employee_id` int UNSIGNED NOT NULL,
  `task_id` int UNSIGNED NOT NULL,
  `action` enum('start','complete') COLLATE utf8mb4_unicode_ci NOT NULL,
  `at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `employee_id` (`employee_id`),
  KEY `task_id` (`task_id`),
  KEY `action` (`action`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
CREATE TABLE IF NOT EXISTS `users` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
  `username` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('admin','editor','employee','user') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'user',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `employee_id` int UNSIGNED DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `idx_users_employee_id` (`employee_id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`id`, `username`, `password_hash`, `role`, `is_active`, `employee_id`, `created_at`, `updated_at`) VALUES
(1, 'admin', '8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918', 'admin', 1, NULL, '2025-08-27 19:40:56', '2025-08-27 19:40:56');

-- --------------------------------------------------------

--
-- Table structure for table `user_policy_consents`
--

DROP TABLE IF EXISTS `user_policy_consents`;
CREATE TABLE IF NOT EXISTS `user_policy_consents` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id` int UNSIGNED NOT NULL,
  `policy_version` varchar(20) NOT NULL,
  `accepted_at` datetime NOT NULL,
  `ip` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `tasks`
--
ALTER TABLE `tasks`
  ADD CONSTRAINT `fk_tasks_employee` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE SET NULL;

--
-- Constraints for table `task_time_logs`
--
ALTER TABLE `task_time_logs`
  ADD CONSTRAINT `fk_ttl_emp` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_ttl_task` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `users`
--
ALTER TABLE `users`
  ADD CONSTRAINT `fk_users_employee` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE SET NULL;

--
-- Constraints for table `user_policy_consents`
--
ALTER TABLE `user_policy_consents`
  ADD CONSTRAINT `user_policy_consents_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
