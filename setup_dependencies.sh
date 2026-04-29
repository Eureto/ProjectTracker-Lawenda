#!/bin/bash

# Exit on error
set -e

echo "--- Starting Buildozer Dependency Setup ---"

# 1. Define required system packages
PACKAGES=(
    zip unzip openjdk-17-jdk python3-pip 
    python3-virtualenv autoconf libtool pkg-config zlib1g-dev 
    libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev 
    libssl-dev automake autopoint gettext
)

echo "[INFO] Updating package lists..."
sudo apt-get update

echo "[INFO] Checking and installing system packages..."
for pkg in "${PACKAGES[@]}"; do
    if dpkg -s "$pkg" >/dev/null 2>&1; then
        echo "[SKIPPED] $pkg is already installed."
    else
        echo "[INSTALLING] $pkg..."
        sudo apt-get install -y "$pkg"
    fi
done

# 2. Configure Java Alternatives
echo "[INFO] Configuring Java 17 alternatives..."

# Function to set alternative if version 17 is found
set_java_17() {
    local bin=$1
    local path=$(update-alternatives --list "$bin" 2>/dev/null | grep "java-17" | head -n 1)
    if [ -n "$path" ]; then
        echo "[SETTING] $bin to $path"
        sudo update-alternatives --set "$bin" "$path"
    else
        echo "[WARN] Java 17 path for $bin not found automatically."
        echo "[ACTION] Please run: sudo update-alternatives --config $bin"
    fi
}

set_java_17 "java"
set_java_17 "javac"

# 3. Install Rust
if command -v rustc >/dev/null 2>&1; then
    echo "[SKIPPED] Rust is already installed."
else
    echo "[INSTALLING] Rust (default option)..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
fi

# 4. Configure Bash Environment
echo "[INFO] Configuring ~/.bashrc for Rust environment..."
RUST_ENV_LINE='. "$HOME/.cargo/env"'

if grep -qxF "$RUST_ENV_LINE" ~/.bashrc; then
    echo "[SKIPPED] Rust env line already exists in ~/.bashrc"
else
    echo "[ADDING] Rust env line to ~/.bashrc"
    echo "" >> ~/.bashrc
    echo "# Rust environment for Buildozer" >> ~/.bashrc
    echo "$RUST_ENV_LINE" >> ~/.bashrc
fi

echo "------------------------------------------------"
echo "---           SETUP COMPLETE                 ---"
echo "------------------------------------------------"
echo "[IMPORTANT] Run the following command to refresh your current shell:"
echo "source ~/.bashrc"
echo ""
echo "Current Java Version:"
java -version
echo ""
echo "Current Rust Version:"
source "$HOME/.cargo/env" && rustc --version
