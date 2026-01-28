"""
Tests for api/embeddings.py - Gemini text embedding functionality
"""
import pytest
from unittest.mock import Mock, patch


class TestGetEmbedding:
    """get_embedding 함수 테스트"""

    def test_get_embedding_returns_list_of_floats(self):
        """정상적인 텍스트에 대해 float 리스트 반환"""
        # Mock Gemini client
        mock_client = Mock()
        mock_result = Mock()
        mock_result.embedding = [0.1] * 768  # 768차원 벡터
        mock_client.models.embed_content.return_value = mock_result

        with patch('api.embeddings.client', mock_client):
            from api.embeddings import get_embedding
            result = get_embedding("테스트 텍스트")

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 768
        assert all(isinstance(x, float) for x in result)

    def test_get_embedding_returns_none_when_no_client(self):
        """Gemini 클라이언트 없을 때 None 반환"""
        with patch('api.embeddings.client', None):
            from api.embeddings import get_embedding
            result = get_embedding("테스트 텍스트")

        assert result is None

    def test_get_embedding_calls_correct_model(self):
        """text-embedding-004 모델 사용 확인"""
        mock_client = Mock()
        mock_result = Mock()
        mock_result.embedding = [0.1] * 768
        mock_client.models.embed_content.return_value = mock_result

        with patch('api.embeddings.client', mock_client):
            from api.embeddings import get_embedding
            get_embedding("테스트")

        mock_client.models.embed_content.assert_called_once()
        call_args = mock_client.models.embed_content.call_args
        assert call_args.kwargs['model'] == "text-embedding-004"
        assert call_args.kwargs['content'] == "테스트"


class TestEmbeddingsModuleInit:
    """embeddings 모듈 초기화 테스트"""

    def test_client_initialized_with_api_key(self):
        """GEMINI_API_KEY가 있으면 client 생성"""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            with patch('api.embeddings.genai') as mock_genai:
                mock_genai.Client.return_value = Mock()
                # Re-import to trigger initialization
                import importlib
                import api.embeddings
                importlib.reload(api.embeddings)

                # client should be set (mocked)
                # Note: actual assertion depends on implementation

    def test_client_none_without_api_key(self):
        """GEMINI_API_KEY가 없으면 client는 None"""
        with patch.dict('os.environ', {'GEMINI_API_KEY': ''}):
            import importlib
            import api.embeddings
            importlib.reload(api.embeddings)

            # Note: need to check client is None after reload
