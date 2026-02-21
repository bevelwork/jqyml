.PHONY: run test

run:
	jq -R -s -rf run.jq < test.yml

# Run YAML parser against all test files in tests/
TEST_YAMLS := $(wildcard tests/*.yaml)
test:
	@failed=0; \
	for f in $(TEST_YAMLS); do \
	  echo "Testing $$f..."; \
	  jq -R -s -rf run.jq < "$$f" > /dev/null || { echo "  FAILED"; failed=$$((failed+1)); }; \
	done; \
	[ $$failed -eq 0 ] && echo "All tests passed." || { echo "$$failed test(s) failed."; exit 1; }
