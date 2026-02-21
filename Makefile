.PHONY: run test

run:
	jq -R -s -rf run.jq < test.yml

# Run YAML parser against all test files in tests/
# Test 14 (anchors) is expected to exit non-zero; others must parse successfully.
TEST_YAMLS := $(wildcard tests/*.yaml)
test:
	@failed=0; \
	for f in $(TEST_YAMLS); do \
	  echo "Testing $$f..."; \
	  jq -R -s -rf run.jq < "$$f" >/dev/null 2>&1; ret=$$?; \
	  if basename "$$f" | grep -q '14_anchors'; then \
	    if [ $$ret -eq 0 ]; then echo "  FAILED (expected anchor rejection)"; failed=$$((failed+1)); fi; \
	  else \
	    if [ $$ret -ne 0 ]; then echo "  FAILED"; failed=$$((failed+1)); fi; \
	  fi; \
	done; \
	[ $$failed -eq 0 ] && echo "All tests passed." || { echo "$$failed test(s) failed."; exit 1; }
