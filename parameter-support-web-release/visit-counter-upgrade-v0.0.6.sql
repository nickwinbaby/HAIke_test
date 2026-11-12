USE parameter_support_stats;

CREATE TABLE IF NOT EXISTS visit_details (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  visited_at DATETIME NOT NULL,
  ip_address VARCHAR(45) NOT NULL,
  location VARCHAR(255) NOT NULL DEFAULT '未知',
  PRIMARY KEY (id),
  KEY idx_visited_at (visited_at),
  KEY idx_ip_address (ip_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ip_location_cache (
  ip_address VARCHAR(45) NOT NULL,
  location VARCHAR(255) NOT NULL DEFAULT '未知',
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (ip_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

GRANT SELECT, INSERT, UPDATE ON parameter_support_stats.*
  TO 'parameter_stats'@'127.0.0.1';
FLUSH PRIVILEGES;
