.PHONY: run test up send docker-up docker-down docker-send

JQYML_DIR := $(CURDIR)
PORT := 8888

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

up:
	docker compose up -d --build

down:
	docker compose down

# POST test.yml to containerized service (run "make up" first).
send:
	@curl -s -S --connect-timeout 5 --max-time 15 -X POST --data-binary @test.yml http://localhost:8080/
