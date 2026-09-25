import unittest
from datetime import date
from unittest.mock import patch, AsyncMock, MagicMock
from services import vocabulary as v


class VocabularyTests(unittest.IsolatedAsyncioTestCase):
    def test_daily_and_short_and_sunday(self):
        with patch.object(v, 'today', return_value=date(2026, 9, 25)):
            state = dict(words={}, sessions={}, reviews=[])
            s = v.session(state, short=True)
            self.assertEqual(len(s['new']), 3)
            self.assertIs(v.session(state), s)
        with patch.object(v, 'today', return_value=date(2026, 9, 27)):
            self.assertEqual(v.session(state)['new'], [])

    async def test_reveal_grade_and_stale_click(self):
        state = dict(words={'1': dict(due='2026-09-24', introduced='2026-09-20', streak=0)},
                     sessions={}, reviews=[])
        q = MagicMock()
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        q.message.reply_text = AsyncMock()
        update = MagicMock(callback_query=q)
        with patch.object(v, 'today', return_value=date(2026, 9, 25)), \
             patch.object(v, 'load', return_value=state), patch.object(v, 'save'):
            q.data = 'voc:reveal:2026-09-25:0'
            await v.callback(update, None)
            q.data = 'voc:yes:2026-09-25:0'
            await v.callback(update, None)
            self.assertEqual(state['words']['1']['due'], '2026-09-28')
            self.assertEqual(len(state['reviews']), 1)
            await v.callback(update, None)
            self.assertEqual(len(state['reviews']), 1)
            q.message.reply_text.assert_awaited_once()

    def test_pool_integrity(self):
        self.assertEqual(len(v.WORDS), 48)
        self.assertEqual(len(v.BY_ID), 48)
        self.assertTrue(all(w['example'] and w['turkish'] for w in v.WORDS))
