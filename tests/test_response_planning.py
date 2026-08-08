import unittest

from src.conversation import ConversationSession, RecentExchangeKind
from src.response_planning import ResponsePlanner, ResponsePurpose


class ResponsePlanningTests(unittest.TestCase):
    def setUp(self):
        self.planner = ResponsePlanner()

    def test_qualified_creative_requests_are_creative(self):
        prompts = (
            "İki cümləlik qısa hekayə yaz.",
            "Mənə qısa bir hekayə yaz.",
            "Kədərli bir mahnı yaz.",
            "Üç bəndlik şeir yaz.",
            "Mənim üçün balaca bir hekayə qur.",
            "Bir mahnı sözləri yaz.",
            "Qısa dialoq yaz.",
            "Bu mövzuda kiçik hekayə yaz.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertIs(
                    self.planner.plan(prompt, ConversationSession().snapshot()).purpose,
                    ResponsePurpose.CREATIVE,
                )

    def test_non_creative_similar_words_remain_general(self):
        prompts = (
            "Hekayə nədir?",
            "Bu hekayəni izah et.",
            "Şeir necə yazılır?",
            "Mahnı haqqında məlumat ver.",
            "Yazı bacarığını necə inkişaf etdirmək olar?",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertIs(
                    self.planner.plan(prompt, ConversationSession().snapshot()).purpose,
                    ResponsePurpose.GENERAL,
                )

    def test_modifier_after_creative_exchange_is_continuation(self):
        session = ConversationSession()
        session.append_complete(
            RecentExchangeKind.CONVERSATION,
            "İki cümləlik qısa hekayə yaz.",
            "Birinci cümlə. İkinci cümlə.",
        )
        for modifier in ("Kədərli olsun.", "Daha qısa et.", "Davam et.", "Biraz daha ciddi olsun."):
            with self.subTest(modifier=modifier):
                self.assertIs(
                    self.planner.plan(modifier, session.snapshot()).purpose,
                    ResponsePurpose.CONTINUATION,
                )

    def test_modifier_after_command_is_not_continuation(self):
        session = ConversationSession()
        session.append_complete(RecentExchangeKind.COMMAND, "/fact list", "Fakt yoxdur.")
        self.assertIs(
            self.planner.plan("Davam et.", session.snapshot()).purpose,
            ResponsePurpose.GENERAL,
        )


if __name__ == "__main__":
    unittest.main()
