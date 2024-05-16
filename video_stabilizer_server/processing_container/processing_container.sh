#!/bin/bash

python /app/smooth_server.zip &
python /app/flow_server.zip &
python /app/cumsum_server.zip &

# Testing purposes
# python smooth_server.zip &
# python flow_server.zip &
# python cumsum_server.zip &

# print
echo "All servers are running"

# Wait for all background processes to finish
wait

# Exit with success status
exit 0
