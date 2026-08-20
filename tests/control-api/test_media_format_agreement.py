"""What Asterisk is told to play must equal what the partner is told to send."""

from types import SimpleNamespace

from app.call_media import CallMedia
from gateway.audiosocket import channel_format


def _media(transport: str, rate: int) -> CallMedia:
    instance = CallMedia.__new__(CallMedia)
    instance.settings = SimpleNamespace(
        media_transport=transport,
        media_sample_rate=rate,
        audiosocket_advertise_host="api",
        audiosocket_port=8090,
    )
    return instance


class TestAdvertisedFormatMatchesTheChannel:
    def test_audiosocket_advertises_the_rate_it_asks_asterisk_for(self):
        """These drifted apart once and the caller heard the difference."""
        for rate in (8000, 16000):
            media = _media("audiosocket", rate)
            assert media.wire_format() == {
                "encoding": "pcm_s16le",
                "sample_rate": rate,
                "channels": 1,
            }
            assert channel_format(rate) in f"c({channel_format(rate)})"

    def test_external_media_advertises_mulaw_not_the_audiosocket_rate(self):
        """That leg is negotiated as ulaw/8000 whatever the slin rate says."""
        media = _media("externalmedia", 16000)
        assert media.wire_format() == {
            "encoding": "pcm_mulaw",
            "sample_rate": 8000,
            "channels": 1,
        }

    def test_the_default_deployment_is_narrowband_end_to_end(self):
        from app.settings import get_settings

        assert get_settings().media_sample_rate == 8000
