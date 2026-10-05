import unittest
from app import app, build_result, study_summary

class EnemLogicTests(unittest.TestCase):
    def setUp(self):
        self.exam = {
            "questions": [
                {"numero": 1, "resposta": "A"},
                {"numero": 2, "resposta": "B"},
                {"numero": 46, "resposta": "C"},
            ],
            "answers": {"1": "A", "2": "D", "46": "C"},
            "chutes": {2},
        }

    def test_build_result_marks_correct_wrong_chute_and_area(self):
        rows = build_result(self.exam)
        self.assertTrue(rows[0]["ok"])
        self.assertFalse(rows[1]["ok"])
        self.assertTrue(rows[1]["chute"])
        self.assertEqual(rows[0]["area"], "Linguagens")
        self.assertEqual(rows[2]["area"], "Ciências Humanas")

    def test_study_summary_prioritizes_errors_and_chutes(self):
        summary = study_summary(self.exam)
        self.assertIn("Linguagens", summary)
        self.assertEqual(summary["Linguagens"]["wrong"], 1)
        self.assertIn(2, summary["Linguagens"]["questions"])
        self.assertNotIn("Ciências Humanas", summary)

    def test_home_route_is_available(self):
        client = app.test_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)

if __name__ == "__main__":
    unittest.main()
