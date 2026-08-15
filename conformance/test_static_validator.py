import copy
import unittest

from .static_validator import FixtureError, load_fixture, validate_fixture

class StaticFixtureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture()

    def assert_invalid(self, mutate):
        candidate = copy.deepcopy(self.fixture)
        mutate(candidate)
        with self.assertRaises(FixtureError):
            validate_fixture(candidate)

    def test_canonical_fixture_is_valid(self):
        self.assertTrue(validate_fixture(self.fixture))

    def test_valid_unused_property_is_allowed(self):
        self.fixture["facts"].append({
            "id": "fact:r2-unused",
            "kind": "property",
            "description": "realization:r2",
            "property": "unused-property",
            "value": {"kind": "symbol", "value": "ignored"},
            "scope": "catalog",
            "epistemic_status": "exact",
            "provenance": ["source:m1-fixture"],
        })
        self.assertTrue(validate_fixture(self.fixture))

    def test_identifier_and_reference_checks(self):
        self.assert_invalid(lambda f: f["descriptions"].append(f["descriptions"][0]))
        self.assert_invalid(lambda f: f["facts"][0].update(description="description:missing"))
        self.assert_invalid(lambda f: f["relations"][0].update(participants=["realization:r1"]))
        self.assert_invalid(lambda f: f["contexts"][0].update(enabled_rules=["rule:missing"]))

    def test_value_contract(self):
        self.assert_invalid(lambda f: f["facts"][4]["value"].update(value=True))
        self.assert_invalid(lambda f: f["facts"][4]["value"].update(value="01"))
        self.assert_invalid(lambda f: f["facts"][0]["value"].update(items=["a", "a"]))
        sequence = {"kind": "sequence<symbol>", "items": ["a", "a"]}
        self.fixture["facts"][0]["value"] = sequence
        self.fixture["vocabulary"]["properties"][1]["value"] = "sequence<symbol>"
        self.assertTrue(validate_fixture(self.fixture))

    def test_required_metadata(self):
        self.assert_invalid(lambda f: f["facts"][0].pop("provenance"))
        self.assert_invalid(lambda f: f["relations"][0].update(epistemic_status="not-a-status"))
        self.assert_invalid(lambda f: f["facts"][0].update(scope=""))

    def test_supersession_compact_form(self):
        self.assertTrue(validate_fixture(self.fixture))
        self.assert_invalid(lambda f: f["supersession"].update(replaces="fact:missing"))
        self.assert_invalid(lambda f: f["supersession"].update(replacement_id="fact:r1-cost"))
        self.assert_invalid(lambda f: f["supersession"].update(
            replacement_value={"kind": "integer", "value": "2"}))

    def test_schema_and_required_sections(self):
        self.assert_invalid(lambda f: f.update(schema="wrong/1"))
        self.assert_invalid(lambda f: f.pop("vocabulary"))
        self.assert_invalid(lambda f: f["rules"][0]["head"].update(participants=["request", "candidate"]))


if __name__ == "__main__":
    unittest.main()
