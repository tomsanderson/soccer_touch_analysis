import unittest

from backend import parser


class ParserSpecTests(unittest.TestCase):
    def test_first_touch_parsing(self) -> None:
        segments = [
            {"start": 10.2, "end": 11.0, "text": "Blue seven first touch high, controlled."},
        ]

        events = parser.parse_transcript_segments(
            segments, match_id="match-1", period="1", offset_seconds=0.0
        )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["event_type"], "first_touch")
        self.assertEqual(event["team"], "Blue")
        self.assertEqual(event["player_jersey_number"], "7")
        self.assertEqual(event["first_touch_quality"], "high")
        self.assertEqual(event["first_touch_result"], "controlled")
        self.assertTrue(event["maintained_possession_bool"])

    def test_on_ball_action_parsing(self) -> None:
        segments = [
            {"start": 10.2, "end": 11.0, "text": "Blue seven first touch high, controlled."},
            {
                "start": 13.5,
                "end": 15.2,
                "text": "Blue seven two-touch pass, safe recycle to center back, completed.",
            },
        ]

        events = parser.parse_transcript_segments(
            segments, match_id="match-1", period="1", offset_seconds=0.0
        )

        self.assertEqual(len(events), 2)
        action_event = events[1]
        self.assertEqual(action_event["event_type"], "on_ball_action")
        self.assertEqual(action_event["touch_count_before_action"], "two_touch")
        self.assertEqual(action_event["on_ball_action_type"], "pass")
        self.assertEqual(action_event["pass_intent"], "safe_recycle")
        self.assertEqual(action_event["action_outcome_team"], "same_team")
        self.assertEqual(action_event["action_outcome_detail"], "completed")

    def test_post_loss_reaction_parsing(self) -> None:
        segments = [
            {
                "start": 10.2,
                "end": 11.0,
                "text": "Blue seven first touch low, rebound to opponent.",
            },
            {
                "start": 17.0,
                "end": 18.5,
                "text": "After losing it, Blue seven immediate press, wins it back herself.",
            },
        ]

        events = parser.parse_transcript_segments(
            segments, match_id="match-55", period="2", offset_seconds=0.0
        )

        self.assertEqual(len(events), 2)
        loss_event = events[0]
        reaction_event = events[1]
        self.assertEqual(loss_event["event_type"], "first_touch")
        self.assertEqual(reaction_event["event_type"], "post_loss_reaction")
        self.assertEqual(
            reaction_event["trigger_event_id"],
            loss_event["event_id"],
        )
        self.assertEqual(reaction_event["post_loss_behaviour"], "immediate_press")
        self.assertEqual(reaction_event["post_loss_outcome"], "won_back_possession_self")
        self.assertEqual(reaction_event["post_loss_effort_intensity"], "high")

    def test_multi_sentence_segment(self) -> None:
        segments = [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "Blue 7, first touch high, controlled. Blue 7, two touch pass, safe recycle to center back, completed.",
            }
        ]

        events = parser.parse_transcript_segments(
            segments, match_id="match-2", period="1", offset_seconds=0.0
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event_type"], "first_touch")
        self.assertEqual(events[1]["event_type"], "on_ball_action")


if __name__ == "__main__":
    unittest.main()
