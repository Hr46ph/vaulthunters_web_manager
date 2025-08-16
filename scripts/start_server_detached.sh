#!/bin/bash

# VaultHunters Server Detached Launcher
# This script starts the Minecraft server in a way that survives web app restarts

SERVER_PATH="$1"
JAVA_EXECUTABLE="$2"
shift 2
FORGE_ARGS="$@"

if [ -z "$SERVER_PATH" ] || [ -z "$JAVA_EXECUTABLE" ]; then
    echo "Usage: $0 <server_path> <java_executable> <forge_args...>"
    exit 1
fi

cd "$SERVER_PATH" || exit 1

# Create logs directory if it doesn't exist
mkdir -p logs

# Start the server completely detached using multiple techniques
# 1. setsid creates new session
# 2. nohup ignores SIGHUP 
# 3. disown removes from job control
# 4. Background execution with &
(
    setsid nohup "$JAVA_EXECUTABLE" $FORGE_ARGS >> logs/latest.log 2>&1 </dev/null &
    disown
) &

echo "Server started with fully detached process"