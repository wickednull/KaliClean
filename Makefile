.PHONY: all icons deb install uninstall clean check

all: deb

## Regenerate PNG icons from assets/kaliclean.svg (requires PySide6).
icons:
	python3 assets/render_icons.py

## Build dist/kaliclean_<version>_all.deb. Override with: make deb VERSION=1.1.0
deb:
	./packaging/build_deb.sh $(VERSION)

## Quick system install without a package.
install:
	sudo ./install.sh

uninstall:
	sudo ./uninstall.sh

check:
	python3 -m py_compile kaliclean.py backend.py assets/render_icons.py
	bash -n install.sh uninstall.sh packaging/build_deb.sh packaging/postinst packaging/postrm

clean:
	rm -rf dist __pycache__ assets/__pycache__
