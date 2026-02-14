"""Tests for SafetyConstraints."""


class TestSafetyConstraints:
    def test_passes_valid_recommendation(self, constraints):
        rec = {
            "passive_time": 2.0,
            "active_creation": 2.0,
            "social_time": 1.0,
            "physical_time": 1.0,
        }
        result = constraints.apply_constraints(rec)
        assert "_adjusted" not in result

    def test_adjusts_excessive_passive_time(self, constraints):
        rec = {
            "passive_time": 8.0,
            "active_creation": 2.0,
            "social_time": 1.0,
            "physical_time": 1.0,
        }
        result = constraints.apply_constraints(rec)
        assert result["_adjusted"] is True
        assert result["passive_time"] <= constraints.constraints["max_passive_time"]

    def test_adjusts_insufficient_active_creation(self, constraints):
        rec = {
            "passive_time": 2.0,
            "active_creation": 0.0,
            "social_time": 1.0,
            "physical_time": 1.0,
        }
        result = constraints.apply_constraints(rec)
        assert result["_adjusted"] is True
        assert result["active_creation"] >= constraints.constraints["min_active_creation"]

    def test_custom_constraints(self):
        custom = SafetyConstraints({"max_passive_time": 2.0, "min_active_creation": 3.0,
                                     "social_interaction_min": 1.0, "physical_activity_min": 1.0})
        rec = {"passive_time": 3.0, "active_creation": 1.0, "social_time": 1.0, "physical_time": 1.0}
        result = custom.apply_constraints(rec)
        assert result["_adjusted"] is True


from resonance_alignment.safety.constraints import SafetyConstraints
