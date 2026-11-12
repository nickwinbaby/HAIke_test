USE parameter_support_stats;

ALTER TABLE visit_details
  ADD COLUMN device_info VARCHAR(255) NOT NULL DEFAULT '未知设备' AFTER location;
