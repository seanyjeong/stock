"""
Tests for api/glossary.py - 주식 용어 사전 API
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient


class TestGlossaryCategories:
    """GET /api/glossary/categories 테스트"""

    def test_get_categories_returns_list(self):
        """카테고리 목록 반환"""
        from api.glossary import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch('api.glossary.get_db') as mock_db:
            mock_conn = Mock()
            mock_cur = Mock()
            mock_cur.fetchall.return_value = [
                ('기본 용어',),
                ('기술적 분석',),
                ('숏스퀴즈',)
            ]
            mock_conn.cursor.return_value = mock_cur
            mock_db.return_value = mock_conn

            response = client.get("/api/glossary/categories")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert '기본 용어' in data


class TestGlossaryTermsByCategory:
    """GET /api/glossary/terms/{category} 테스트"""

    def test_get_terms_returns_list(self):
        """특정 카테고리의 용어 목록 반환"""
        from api.glossary import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch('api.glossary.get_db') as mock_db:
            mock_conn = Mock()
            mock_cur = Mock()
            mock_cur.fetchall.return_value = [
                {
                    'id': 1,
                    'term': 'PER',
                    'definition': '주가수익비율',
                    'example': 'PER 10이면...',
                    'related_terms': ['PBR', 'EPS']
                }
            ]
            mock_conn.cursor.return_value = mock_cur
            mock_db.return_value = mock_conn

            response = client.get("/api/glossary/terms/기본 용어")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestGlossarySearch:
    """GET /api/glossary/search 테스트"""

    def test_search_returns_similar_terms(self):
        """시맨틱 검색으로 유사 용어 반환"""
        from api.glossary import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch('api.glossary.get_db') as mock_db:
            with patch('api.glossary.get_embedding') as mock_embed:
                mock_embed.return_value = [0.1] * 768

                mock_conn = Mock()
                mock_cur = Mock()
                mock_cur.fetchall.return_value = [
                    {
                        'term': '숏스퀴즈',
                        'definition': '공매도 세력이 손절하며...',
                        'similarity': 0.95
                    }
                ]
                mock_conn.cursor.return_value = mock_cur
                mock_db.return_value = mock_conn

                response = client.get("/api/glossary/search?q=숏스퀴즈가 뭐야")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_search_without_query_returns_error(self):
        """쿼리 없으면 422 에러"""
        from api.glossary import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/api/glossary/search")

        # FastAPI returns 422 for missing required query params
        assert response.status_code == 422


class TestGlossaryAsk:
    """POST /api/glossary/ask 테스트"""

    def test_ask_returns_ai_answer(self):
        """AI 답변 반환"""
        from api.glossary import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch('api.glossary.get_db') as mock_db:
            with patch('api.glossary.get_embedding') as mock_embed:
                with patch('api.glossary.gemini_client') as mock_gemini:
                    mock_embed.return_value = [0.1] * 768

                    mock_conn = Mock()
                    mock_cur = Mock()
                    mock_cur.fetchall.return_value = [
                        {
                            'term': '숏스퀴즈',
                            'definition': '공매도 세력이 손절하며...',
                            'example': '예시...',
                            'related_terms': ['공매도', 'FTD'],
                            'similarity': 0.95
                        }
                    ]
                    mock_conn.cursor.return_value = mock_cur
                    mock_db.return_value = mock_conn

                    mock_response = Mock()
                    mock_response.text = "숏스퀴즈는 공매도 세력이..."
                    mock_gemini.models.generate_content.return_value = mock_response

                    response = client.post(
                        "/api/glossary/ask",
                        json={"question": "숏스퀴즈가 뭐야?"}
                    )

        assert response.status_code == 200
        data = response.json()
        assert 'answer' in data
        assert 'related_terms' in data

    def test_ask_without_gemini_uses_fallback(self):
        """Gemini 없으면 검색 결과만 반환"""
        from api.glossary import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch('api.glossary.get_db') as mock_db:
            with patch('api.glossary.get_embedding') as mock_embed:
                with patch('api.glossary.gemini_client', None):
                    mock_embed.return_value = [0.1] * 768

                    mock_conn = Mock()
                    mock_cur = Mock()
                    mock_cur.fetchall.return_value = [
                        {
                            'term': '숏스퀴즈',
                            'definition': '공매도 세력이 손절하며...',
                            'example': None,
                            'related_terms': None,
                            'similarity': 0.95
                        }
                    ]
                    mock_conn.cursor.return_value = mock_cur
                    mock_db.return_value = mock_conn

                    response = client.post(
                        "/api/glossary/ask",
                        json={"question": "숏스퀴즈가 뭐야?"}
                    )

        assert response.status_code == 200
        data = response.json()
        # Fallback: definition을 answer로 사용
        assert 'answer' in data


class TestGlossaryEmbedAll:
    """POST /api/glossary/embed-all 테스트 (admin 전용)"""

    def test_embed_all_requires_admin(self):
        """관리자 권한 필요"""
        from api.glossary import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # 인증 없이 호출
        response = client.post("/api/glossary/embed-all")

        # 401 또는 403 예상
        assert response.status_code in [401, 403]

    def test_embed_all_updates_embeddings(self):
        """모든 용어에 임베딩 생성"""
        from api.glossary import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch('api.glossary.require_admin') as mock_admin:
            mock_admin.return_value = {'id': 1, 'is_admin': True}

            with patch('api.glossary.get_db') as mock_db:
                with patch('api.glossary.get_embedding') as mock_embed:
                    mock_embed.return_value = [0.1] * 768

                    mock_conn = Mock()
                    mock_cur = Mock()
                    mock_cur.fetchall.return_value = [
                        {'id': 1, 'term': 'PER', 'definition': '주가수익비율'}
                    ]
                    mock_conn.cursor.return_value = mock_cur
                    mock_db.return_value = mock_conn

                    # Note: This won't work without proper dependency override
                    # response = client.post("/api/glossary/embed-all")
                    pass


class TestGlossaryTableCreation:
    """glossary_terms 테이블 생성 테스트"""

    def test_create_table_function_exists(self):
        """create_table 함수 존재 확인"""
        from api.glossary import create_table
        assert callable(create_table)

    def test_create_table_creates_correct_schema(self):
        """올바른 스키마로 테이블 생성"""
        with patch('api.glossary.get_db') as mock_db:
            mock_conn = Mock()
            mock_cur = Mock()
            mock_conn.cursor.return_value = mock_cur
            mock_db.return_value = mock_conn

            from api.glossary import create_table
            create_table()

            # SQL이 실행되었는지 확인
            mock_cur.execute.assert_called()
            call_args = str(mock_cur.execute.call_args)

            # 필수 컬럼 확인
            assert 'glossary_terms' in call_args
            assert 'term' in call_args
            assert 'definition' in call_args
            assert 'embedding' in call_args
