# Build flow for the dr-tools RPM.
#
# Usage:
#   make wheels    # populate ../dist/wheelhouse with every runtime dep
#   make tarball   # create the SRPM source tarball
#   make srpm      # build the .src.rpm (also runs `make tarball`)
#   make rpm       # build the binary .rpm (also runs `make srpm`)
#   make clean     # nuke build artefacts
#   make install   # install the freshly-built binary RPM via sudo
#
# Quick path from a clean checkout:
#   cd packaging && make rpm
#
# Output:
#   ../dist/wheelhouse/*.whl   — bundled dependency wheels
#   ./rpmbuild/SRPMS/*.src.rpm — source RPM
#   ./rpmbuild/RPMS/x86_64/*.rpm — binary RPM ready to install

NAME    := dr-tools
VERSION := $(shell awk -F'"' '/^__version__/ {print $$2}' ../__version__.py)
PYTHON  := /usr/bin/python3
TOPDIR  := $(CURDIR)/rpmbuild
REPO    := $(realpath $(CURDIR)/..)

# Files included in the source tarball. The wheelhouse is bundled so
# the RPM build is fully offline-reproducible.
TARBALL := $(NAME)-$(VERSION).tar.gz

.PHONY: all wheels tarball srpm rpm clean install help

help:
	@echo "Targets: wheels tarball srpm rpm install clean"
	@echo "Current version: $(VERSION)"

# ---------------------------------------------------------- wheels
# `pip wheel` fetches sdists + binary wheels from PyPI and produces
# ready-to-install .whl files. We re-use the project venv if it exists
# (faster — psycopg2/psutil build deps are cached), else use system pip.
#
# Only `install_requires` from setup.cfg is bundled — dev-only deps
# (pytest, playwright, mitmproxy) stay out of the RPM. To get those
# locally use `pip install -e .[dev]`.
wheels:
	@echo "Building wheelhouse for $(NAME)-$(VERSION)…"
	@rm -rf $(REPO)/dist/wheelhouse
	@mkdir -p $(REPO)/dist/wheelhouse
	@if [ -x $(REPO)/.venv/bin/pip ]; then \
	    PIP=$(REPO)/.venv/bin/pip ; \
	else \
	    PIP="$(PYTHON) -m pip" ; \
	fi ; \
	$$PIP wheel \
	    --wheel-dir $(REPO)/dist/wheelhouse \
	    $(REPO)
	@echo "Wheelhouse populated ($(words $(wildcard $(REPO)/dist/wheelhouse/*.whl)) wheels):"
	@ls -1 $(REPO)/dist/wheelhouse | sed 's/^/  /'

# ---------------------------------------------------------- tarball
# Pack the repo + wheelhouse into the source tarball rpmbuild needs.
# We do this with a `git archive`-style copy that excludes .git, .venv,
# tests, misc, …
tarball: wheels
	@echo "Creating $(TARBALL)…"
	@rm -rf /tmp/$(NAME)-$(VERSION)
	@mkdir -p /tmp/$(NAME)-$(VERSION)
	@# rsync everything we want into the staging tree.
	@rsync -a --delete \
	    --exclude '.git/' \
	    --exclude '.venv/' \
	    --exclude '__pycache__/' \
	    --exclude '*.pyc' \
	    --exclude 'misc/' \
	    --exclude 'tests/' \
	    --exclude '.pytest_cache/' \
	    --exclude '*.egg-info/' \
	    --exclude 'packaging/rpmbuild/' \
	    --exclude '.env' \
	    $(REPO)/ /tmp/$(NAME)-$(VERSION)/
	@# Tar it up.
	@mkdir -p $(TOPDIR)/SOURCES
	@tar -C /tmp -czf $(TOPDIR)/SOURCES/$(TARBALL) $(NAME)-$(VERSION)
	@rm -rf /tmp/$(NAME)-$(VERSION)
	@echo "Tarball: $(TOPDIR)/SOURCES/$(TARBALL)"
	@du -h $(TOPDIR)/SOURCES/$(TARBALL)

# ---------------------------------------------------------- SRPM + RPM
srpm: tarball
	@mkdir -p $(TOPDIR)/SPECS $(TOPDIR)/BUILD $(TOPDIR)/SRPMS $(TOPDIR)/RPMS
	@cp $(CURDIR)/$(NAME).spec $(TOPDIR)/SPECS/
	rpmbuild \
	    --define '_topdir $(TOPDIR)' \
	    --define 'version $(VERSION)' \
	    -bs $(TOPDIR)/SPECS/$(NAME).spec
	@echo "SRPM:"
	@ls -la $(TOPDIR)/SRPMS/

rpm: srpm
	rpmbuild \
	    --define '_topdir $(TOPDIR)' \
	    --define 'version $(VERSION)' \
	    -bb $(TOPDIR)/SPECS/$(NAME).spec
	@echo
	@echo "Binary RPM ready:"
	@find $(TOPDIR)/RPMS -name '*.rpm' -exec ls -lh {} \;

# ---------------------------------------------------------- install / clean
install: rpm
	@RPM=$$(find $(TOPDIR)/RPMS -name '$(NAME)-$(VERSION)-*.rpm' | head -1) ; \
	echo "Installing $$RPM" ; \
	sudo dnf install -y "$$RPM"

clean:
	rm -rf $(TOPDIR)
	rm -rf $(REPO)/dist/wheelhouse
	rm -rf $(REPO)/build
	rm -rf $(REPO)/*.egg-info
