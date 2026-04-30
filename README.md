# Kivy Time Tracker

A professional time tracking application built with the Kivy framework. This project is configured for automated deployment to both local PC and Android devices using Buildozer.

## Prerequisites

- **Python 3.8+**
- **Java 17 JDK** (Required for Android builds)
- **ADB** (Android Debug Bridge) installed and in your PATH for hardware deployment.
- **System Dependencies**: For Android compilation on Linux, see the `setup_dependencies.sh` script.

## Installation and Setup

The project uses a `Makefile` to automate environment creation and dependency management.

### 1. Initialize Environment
Run the following command to verify system dependencies (including Java 17), create a virtual environment, and install Kivy, Buildozer, and other Python requirements:

```bash
make prepare
```

## Usage and Deployment

The workflow is designed to be hardware-aware.

### 1. Smart Deployment
The `deploy` command checks for connected Android hardware via `adb`.
- **If a device is connected**: It packages the app, deploys the APK, and runs it on the device.
- **If no device is found**: It falls back to running the application locally on your PC.

```bash
make deploy
```

### 2. Debug Mode
Builds and runs the application with debug-level logging. Like `deploy`, it automatically switches between Android `logcat` and PC console output based on device availability.

```bash
make debug
```

## Additional Commands

- **Run Tests**: Execute the application test suite using `pytest`.
  ```bash
  make test
  ```
- **Clean Artifacts**: Remove build artifacts, temporary caches, and Buildozer app data.
  ```bash
  make clean
  ```