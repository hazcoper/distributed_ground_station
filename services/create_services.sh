#!/bin/bash

# Script to install and set up all systemd service files in the current directory

# Check if the script is run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Use sudo to execute it."
    exit 1
fi

# Directory containing the service files (current directory)
SERVICE_DIR=$(pwd)

echo "Installing and setting up service files in $SERVICE_DIR..."

# Loop through all .service files in the current directory
for service_file in "$SERVICE_DIR"/*.service; do
    if [[ -f "$service_file" ]]; then
        echo "Processing $service_file..."
        
      # Copy the service file to /etc/systemd/system
      cp "$service_file" /etc/systemd/system/
        
      # Set permissions
      chmod 644 /etc/systemd/system/$(basename "$service_file")
        
      # Reload systemd manager configuration
      systemctl daemon-reload
        
      # Enable the service to start on boot
      systemctl enable $(basename "$service_file")
        
      # Start the service
      systemctl start $(basename "$service_file")
        
      echo "Service $(basename "$service_file") has been installed, enabled, and started."
    else
        echo "No service files found in $SERVICE_DIR."
    fi
done

echo "All service files have been processed."
