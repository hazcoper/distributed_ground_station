#!/bin/bash

# Script to reload systemd and restart all active services

# Check if the script is run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Use sudo to execute it."
    exit 1
fi

echo "Reloading systemd manager configuration..."
systemctl daemon-reload

echo "Fetching a list of active services..."
# Get a list of active services
active_services=$(systemctl list-units --type=service --state=active --no-pager --no-legend | awk '{print $1}')

echo "Restarting all active services..."
for service in $active_services; do
    echo "Restarting $service..."
    systemctl restart "$service"
    if [[ $? -eq 0 ]]; then
        echo "Successfully restarted $service"
    else
        echo "Failed to restart $service"
    fi
done

echo "All active services have been restarted."