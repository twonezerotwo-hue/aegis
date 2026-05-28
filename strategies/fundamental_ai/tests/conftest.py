import os
import sys
import pytest

# Test süitinin ana kod dizinlerine (.../src) ve diğer AEGIS microservislerine problemsiz ulaşabilmesi için:
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../consensus_engine/src")))

@pytest.fixture
def mock_redis(mocker):
    """ Tüm redis pub/sub ve cache timeout fonksiyonlarını sanallaştırır """
    return mocker.MagicMock()
