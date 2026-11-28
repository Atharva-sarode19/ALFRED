import unittest

from app.agent.confirmation import CONFIRMATION_PHRASE, Verdict, interpret_reply, is_short_reply


class InterpretReplyTests(unittest.TestCase):
    def test_standard_phrase(self):
        self.assertEqual(CONFIRMATION_PHRASE, "Shall I go ahead, Sir?")

    def test_natural_approvals(self):
        for text in ["Yes", "yes.", "Yeah", "Go ahead", "go ahead, Sir", "Proceed", "Yes please",
                     "Sure", "Okay", "Please do it", "Do it", "Absolutely", "Of course", "Confirm",
                     "Yes, go ahead please", "Alfred, yes"]:
            self.assertEqual(interpret_reply(text), Verdict.APPROVE, text)

    def test_natural_declines(self):
        for text in ["No", "no.", "Nope", "Cancel", "Don't", "Do not", "Don\u2019t do it", "Stop",
                     "Never mind", "nevermind", "Abort", "Negative", "No thanks", "Wait", "Hold on"]:
            self.assertEqual(interpret_reply(text), Verdict.DECLINE, text)

    def test_mixed_answers_decline_rather_than_approve(self):
        for text in ["yes... no, wait", "yes but cancel that", "go ahead, actually no"]:
            self.assertEqual(interpret_reply(text), Verdict.DECLINE, text)

    def test_approval_must_be_only_an_approval(self):
        for text in ["yes delete everything", "go ahead and email my boss", "sure why not do that"]:
            self.assertEqual(interpret_reply(text), Verdict.UNCLEAR, text)

    def test_silence_and_noise_are_never_approval(self):
        for text in ["", "   ", None, "...", "hmm", "uh", "what time is it"]:
            self.assertEqual(interpret_reply(text), Verdict.UNCLEAR, repr(text))

    def test_is_short_reply(self):
        self.assertTrue(is_short_reply("hmm"))
        self.assertTrue(is_short_reply("what was that"))
        self.assertFalse(is_short_reply(""))
        self.assertFalse(is_short_reply("what is the weather in Pune"))


if __name__ == "__main__":
    unittest.main()
