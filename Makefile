# Configuration
PYTHON = ./venv/bin/python3
BUILDOZER = buildozer
ENTRY_POINT = main.py
TEST_DIR = tests

# Hardware Detection: Check for connected Android devices via adb
# 1. adb devices: lists connected hardware
# 2. grep -v: excludes the header and empty lines
# 3. head -n 1: takes the first available device
DEVICE_CONNECTED = $(shell adb devices 2>/dev/null | grep -v "List of devices" | grep -v "^$$" | head -n 1)

.PHONY: help deploy debug test clean logcat

help:
	@echo "Kivy Deployment Automation"
	@echo "--------------------------"
	@echo "  make deploy  - Auto-deploy: Android (if connected) or PC (fallback)"
	@echo "  make debug   - Build & Run with logs: Android (logcat) or PC (debug level)"
	@echo "  make test    - Run project tests using pytest"
	@echo "  make clean   - Remove build artifacts and temporary cache"
	@echo "  make logcat  - Stream Android logs from the device"

deploy:
	@if [ -n "$(DEVICE_CONNECTED)" ]; then \
		echo "[INFO] Android device detected: $(DEVICE_CONNECTED)"; \
		echo "[INFO] Packaging and deploying to device..."; \
		$(BUILDOZER) android debug deploy run; \
	else \
		echo "[WARN] No Android device detected. Deploying to local PC..."; \
		$(PYTHON) $(ENTRY_POINT); \
	fi

debug:
	@if [ -n "$(DEVICE_CONNECTED)" ]; then \
		echo "[INFO] Starting Android Debug Cycle..."; \
		$(BUILDOZER) android debug deploy run logcat; \
	else \
		echo "[INFO] Starting PC Debug Mode..."; \
		KIVY_LOG_LEVEL=debug $(PYTHON) $(ENTRY_POINT); \
	fi

test:
	@echo "[INFO] Executing application tests..."
	@if [ -d "$(TEST_DIR)" ]; then \
		$(PYTHON) -m pytest $(TEST_DIR); \
	else \
		echo "[ERROR] Test directory '$(TEST_DIR)' not found."; \
	fi

clean:
	@echo "[INFO] Cleaning build environment..."
	$(BUILDOZER) appclean
	rm -rf bin/
	find . -type d -name "__pycache__" -exec rm -rf {} +

logcat:
	@if [ -z "$(DEVICE_CONNECTED)" ]; then \
		echo "[ERROR] No device connected. Cannot run logcat."; \
	else \
		$(BUILDOZER) android logcat; \
	fi
