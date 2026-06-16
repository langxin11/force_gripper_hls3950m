.PHONY: test test-firmware test-software docs docs-serve hooks check clean

test: test-firmware test-software

test-firmware:
	cmake -S firmware -B build/firmware
	cmake --build build/firmware
	ctest --test-dir build/firmware --output-on-failure

test-software:
	uv run --project software --extra dev pytest software/tests -v

docs:
	uv run --project software --extra docs mkdocs build --strict

docs-serve:
	uv run --project software --extra docs mkdocs serve

hooks:
	uv run --project software --extra dev pre-commit run --all-files

check: test docs hooks
	uv run --project software --extra dev mypy software/src

clean:
	cmake -E remove_directory build
	# Remove the pre-build/docs MkDocs output during the transition.
	cmake -E remove_directory site
