# Use bash to support 'source' (or '.') inside recipes
SHELL := /bin/bash

# Configuration
VENV = venv
BIN = $(VENV)/bin
ENTRY_POINT = main.py
TEST_DIR = tests
SYSTEM_SETUP = ./setup_dependencies.sh

# Activation command
ACTIVATE = . $(BIN)/activate

# Prefix for commands that need to run inside the activated environment
RUN_ENV = $(ACTIVATE) &&

# Staging dir buildozer clears with Python rmtree before each copy (fails on FUSE/NTFS).
BUILDOZER_APP_DIR = .buildozer/android/app

# Buildozer internal paths that we sometimes nudge to force a partial rebuild.
BUILDOZER_DISTS_DIR = .buildozer/android/platform
ANDROID_GRADLE_BUILD_DIRS = $(BUILDOZER_DISTS_DIR)/build-*/dists/*/build

# Android application id (package.domain + package.name from buildozer.spec)
ANDROID_PACKAGE = $(shell awk -F' = ' '/^package\.domain/ {d=$$2} /^package\.name/ {n=$$2} END {if (d && n) print d"."n}' buildozer.spec)

# Set help as the default command when no arguments are passed
.DEFAULT_GOAL := help

# Hardware Detection: Check for connected Android devices via adb
# 1. adb devices: lists connected hardware
# 2. grep -v: excludes the header and empty lines
# 3. head -n 1: takes the first available device
DEVICE_CONNECTED = $(shell adb devices 2>/dev/null | grep -v "List of devices" | grep -v "^$$" | head -n 1)

.PHONY: help deploy debug test clean deep-clean logcat prepare android-app-reset \
        rebuild-android quick uninstall default

# Detect if Java 17 is already the active version
JAVA_VER_CHECK = $(shell java -version 2>&1 | grep -q "17\." && echo "1" || echo "0")

prepare: ## Verify system and Python dependencies
	@# 1. Ensure system-level dependencies are met, unless skipped or already valid
	@if [ "$(SKIP_SYS_SETUP)" != "1" ] && [ ! -f ".sys_deps_installed" ]; then \
		if [ "$(JAVA_VER_CHECK)" = "0" ]; then \
			echo "[INFO] Java 17 not detected or system check required. Running setup..."; \
			chmod +x $(SYSTEM_SETUP); \
			$(SYSTEM_SETUP); \
		fi; \
		touch .sys_deps_installed; \
	fi
	@# 2. Ensure virtual environment exists
	@if [ ! -d "$(VENV)" ]; then \
		echo "[INFO] Creating virtual environment..."; \
		python3 -m venv $(VENV); \
	fi
	@# 3. Ensure Python dependencies are installed
	@if [ ! -f "$(BIN)/cython" ] || [ ! -f "$(VENV)/.pip_deps_installed" ]; then \
		$(RUN_ENV) ( \
			echo "[INFO] Installing Python dependencies in $$VIRTUAL_ENV..."; \
			pip install --upgrade pip; \
			if [ -f "requirements.txt" ]; then \
				pip install -r requirements.txt; \
			else \
				pip install cython kivy kivymd buildozer pytest; \
			fi; \
			touch "$(VENV)/.pip_deps_installed"; \
		) \
	fi

help: ## Display this help message
	@echo -e "Kivy Deployment Automation\n--------------------------"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

android-app-reset: ## Remove Android app staging dir (fixes buildozer rmtree on FUSE/NTFS)
	@if [ -d "$(BUILDOZER_APP_DIR)" ]; then \
		echo "[INFO] Removing $(BUILDOZER_APP_DIR) (shell rm; Python rmtree fails on large Emoji_PNG here)..."; \
		rm -rf "$(BUILDOZER_APP_DIR)"; \
	fi

deploy: prepare android-app-reset ## Auto-deploy: Android (if connected) or PC (fallback)
	@$(RUN_ENV) if [ -n "$(DEVICE_CONNECTED)" ]; then \
		echo "[INFO] Android device detected: $(DEVICE_CONNECTED)"; \
		echo "[INFO] Packaging and deploying to device..."; \
		buildozer android debug deploy run; \
	else \
		echo "[WARN] No Android device detected. Deploying to local PC..."; \
		python3 $(ENTRY_POINT); \
	fi

quick: prepare ## Fastest Android rebuild (skip staging reset; Python/.kv edits only)
	@if [ -z "$(DEVICE_CONNECTED)" ]; then \
		echo "[ERROR] No Android device detected. Use 'make deploy' on desktop."; \
		exit 1; \
	fi
	@echo "[INFO] Quick rebuild (no staging reset; keeps p4a dist + gradle cache)..."
	@$(RUN_ENV) buildozer android debug deploy run

rebuild-android: prepare android-app-reset ## After buildozer.spec changes (services, permissions, Java); keeps p4a dist
	@echo "[INFO] Forcing Android project regen (Java/manifest re-emit; keeps p4a dist)..."
	@for d in $(ANDROID_GRADLE_BUILD_DIRS); do \
		if [ -d "$$d" ]; then \
			echo "[INFO]   removing $$d"; \
			rm -rf "$$d"; \
		fi; \
	done
	@if [ -z "$(DEVICE_CONNECTED)" ]; then \
		echo "[WARN] No Android device detected. Skipping deploy/run."; \
		$(RUN_ENV) buildozer android debug; \
	else \
		$(RUN_ENV) buildozer android debug deploy run; \
	fi

debug: prepare android-app-reset ## Build & Run with logs: Android (logcat) or PC (debug level)
	@$(RUN_ENV) if [ -n "$(DEVICE_CONNECTED)" ]; then \
		echo "[INFO] Starting Android Debug Cycle..."; \
		buildozer android debug deploy run logcat; \
	else \
		echo "[INFO] Starting PC Debug Mode..."; \
		KIVY_LOG_LEVEL=debug python3 $(ENTRY_POINT); \
	fi

test: prepare ## Run project tests using pytest
	@echo "[INFO] Executing application tests..."
	@$(RUN_ENV) if [ -d "$(TEST_DIR)" ]; then \
		python3 -m pytest $(TEST_DIR); \
	else \
		echo "[ERROR] Test directory '$(TEST_DIR)' not found."; \
	fi

clean: ## Light clean (bin/, staging, __pycache__); keeps p4a dist so next build is fast
	@echo "[INFO] Light clean (keeps p4a dist; use 'make deep-clean' for full reset)..."
	@$(MAKE) android-app-reset
	rm -rf bin/
	find . -type d -name "__pycache__" -exec rm -rf {} +

deep-clean: ## FULL reset incl. p4a dist + native deps; next build is 30-40 minutes
	@echo "[WARN] Deep clean: next build will recompile python-for-android distribution (slow)."
	@$(MAKE) android-app-reset
	@$(RUN_ENV) buildozer appclean
	rm -rf bin/
	find . -type d -name "__pycache__" -exec rm -rf {} +

logcat: prepare ## Stream Android logs from the device
	@$(RUN_ENV) if [ -z "$(DEVICE_CONNECTED)" ]; then \
		echo "[ERROR] No device connected. Cannot run logcat."; \
	else \
		buildozer android logcat; \
	fi

uninstall: ## Remove the app from connected Android device
	@if [ -z "$(DEVICE_CONNECTED)" ]; then \
		echo "[ERROR] No device connected. Cannot uninstall."; \
		exit 1; \
	fi
	@if [ -z "$(ANDROID_PACKAGE)" ]; then \
		echo "[ERROR] Could not read package id from buildozer.spec."; \
		exit 1; \
	fi
	@echo "[INFO] Uninstalling $(ANDROID_PACKAGE) from device..."
	@adb uninstall "$(ANDROID_PACKAGE)" && echo "[INFO] App removed." || echo "[WARN] Uninstall failed (app may not be installed)."
