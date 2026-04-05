import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLISH_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "publish-images.yml"
TEST_STRATEGY_PATH = REPO_ROOT / "docs" / "test-strategy.md"
RELEASE_CHECKLIST_PATH = REPO_ROOT / "docs" / "release-checklist.md"
README_PATH = REPO_ROOT / "README.md"

REQUIRED_SMOKE_ENV_VARS = [
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD",
    "ADMIN_SESSION_SECRET",
    "ADMIN_SESSION_SECURE",
    "API_DOCS_ENABLED",
]


class ReleaseArtifactsTestCase(unittest.TestCase):
    def assert_smoke_doc_is_self_contained(self, content: str) -> None:
        for var_name in REQUIRED_SMOKE_ENV_VARS:
            self.assertIn(f"export {var_name}=", content)
        self.assertIn('--admin-username "${ADMIN_USERNAME}"', content)
        self.assertIn('--admin-password "${ADMIN_PASSWORD}"', content)

    def assert_workflow_step_has_smoke_env(self, workflow: str, step_name: str) -> None:
        step_block = workflow.split(f"name: {step_name}", maxsplit=1)[1]
        step_block = step_block.split("\n      - name:", maxsplit=1)[0]
        for var_name in REQUIRED_SMOKE_ENV_VARS:
            self.assertIn(f"{var_name}:", step_block)
        self.assertIn("GHCR_NAMESPACE:", step_block)
        self.assertIn("IMAGE_TAG:", step_block)
        self.assertIn("WEB_PORT:", step_block)

    def test_publish_workflow_should_run_smoke_before_promote_steps(self):
        workflow = PUBLISH_WORKFLOW_PATH.read_text(encoding="utf-8")
        smoke_idx = workflow.index("name: Smoke GHCR compose deployment")
        backend_promote_idx = workflow.index("name: Promote backend tags after smoke")
        frontend_promote_idx = workflow.index("name: Promote frontend tags after smoke")

        self.assertLess(smoke_idx, backend_promote_idx)
        self.assertLess(smoke_idx, frontend_promote_idx)

    def test_publish_workflow_should_use_sha_tag_for_smoke_image_tag(self):
        workflow = PUBLISH_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("IMAGE_TAG: ${{ steps.prep.outputs.sha_tag }}", workflow)

    def test_publish_workflow_should_keep_required_env_for_all_ghcr_compose_steps(self):
        workflow = PUBLISH_WORKFLOW_PATH.read_text(encoding="utf-8")
        for step_name in (
            "Smoke GHCR compose deployment",
            "Dump GHCR compose logs",
            "Tear down GHCR compose",
        ):
            self.assert_workflow_step_has_smoke_env(workflow, step_name)

    def test_publish_workflow_should_not_include_latest_before_smoke(self):
        workflow = PUBLISH_WORKFLOW_PATH.read_text(encoding="utf-8")
        before_smoke = workflow.split("name: Smoke GHCR compose deployment", maxsplit=1)[0]
        self.assertIn(
            'tags: ghcr.io/${{ steps.prep.outputs.owner_lc }}/fdy-tracker-api:${{ steps.prep.outputs.sha_tag }}',
            before_smoke,
        )
        self.assertIn(
            'tags: ghcr.io/${{ steps.prep.outputs.owner_lc }}/fdy-tracker-web:${{ steps.prep.outputs.sha_tag }}',
            before_smoke,
        )
        self.assertNotIn(":latest", before_smoke)
        self.assertNotIn("${{ github.ref_name }}", before_smoke)
        self.assertNotIn("steps.promote.outputs.target_tag", before_smoke)

    def test_smoke_env_vars_should_be_explicit_in_test_strategy_doc(self):
        content = TEST_STRATEGY_PATH.read_text(encoding="utf-8")
        self.assert_smoke_doc_is_self_contained(content)

    def test_smoke_env_vars_should_be_explicit_in_release_checklist_doc(self):
        content = RELEASE_CHECKLIST_PATH.read_text(encoding="utf-8")
        self.assert_smoke_doc_is_self_contained(content)

    def test_readme_should_document_outbound_proxy_examples(self):
        content = README_PATH.read_text(encoding="utf-8")
        self.assertIn("OUTBOUND_PROXY_URL", content)
        self.assertIn("http://127.0.0.1:7890", content)
        self.assertIn("socks5://127.0.0.1:40000", content)
        self.assertIn("SOCKS5", content)


if __name__ == "__main__":
    unittest.main()
