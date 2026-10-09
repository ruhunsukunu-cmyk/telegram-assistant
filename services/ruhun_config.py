"""Explicit configuration for the single-owner Ruhun bot."""
import os
from dataclasses import dataclass

CHANNEL_ID = 'UCwtUrD_YkZ7xoofBsuwzTMA'

@dataclass(frozen=True)
class Config:
    token: str = ''
    owner_id: int = 0
    chat_id: int = 0
    youtube_client_id: str = ''
    youtube_client_secret: str = ''
    youtube_refresh_token: str = ''
    gemini_key: str = ''
    gemini_model: str = 'gemini-2.5-flash'
    free_tier_verified: bool = False
    free_tier_evidence: str = ''
    jobs_enabled: bool = False
    drop_pending: bool = False

    @property
    def youtube_ready(self):
        return bool(self.youtube_client_id and self.youtube_client_secret and self.youtube_refresh_token)

    @property
    def ai_ready(self):
        return bool(self.gemini_key and self.free_tier_verified and self.free_tier_evidence
                    and self.gemini_model == 'gemini-2.5-flash')

    @classmethod
    def from_env(cls):
        def flag(name):
            return os.getenv(name, '').lower() in ('1', 'true', 'yes')
        return cls(
            token=os.getenv('TELEGRAM_BOT_TOKEN', '').strip(),
            owner_id=int(os.getenv('RUHUN_OWNER_ID', '0') or 0),
            chat_id=int(os.getenv('RUHUN_CHAT_ID', '0') or 0),
            youtube_client_id=os.getenv('RUHUN_YT_CLIENT_ID', '').strip(),
            youtube_client_secret=os.getenv('RUHUN_YT_CLIENT_SECRET', '').strip(),
            youtube_refresh_token=os.getenv('RUHUN_YT_REFRESH_TOKEN', '').strip(),
            gemini_key=os.getenv('RUHUN_GEMINI_API_KEY', '').strip(),
            gemini_model=os.getenv('RUHUN_GEMINI_MODEL', 'gemini-2.5-flash').strip(),
            free_tier_verified=flag('RUHUN_GEMINI_FREE_TIER_VERIFIED'),
            free_tier_evidence=os.getenv('RUHUN_GEMINI_FREE_TIER_EVIDENCE', '').strip(),
            jobs_enabled=flag('RUHUN_JOBS_ENABLED'),
            drop_pending=flag('RUHUN_DROP_PENDING_UPDATES'),
        )
