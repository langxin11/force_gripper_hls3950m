.PHONY: test test-firmware test-software clean

test: test-firmware test-software

test-firmware:
	cmake -S firmware -B build/firmware
	cmake --build build/firmware
	ctest --test-dir build/firmware --output-on-failure

test-software:
	PYTHONPATH=software/src python3 -m unittest discover -s software/tests -v

clean:
	cmake -E remove_directory build
