import jwt

from barug import settings


class Claims:
    
    """
    Use this class to do JWT operations. However, this is subject
    to change and might consider pushing logic to a decorator depending
    on the original author.

    Returns:
        _type_:
            - user_id (int)
    """
    
    JWT_SECRET = settings.SECRET_KEY
    JWT_ALGORITHM = "HS256"

    @classmethod
    def verify_jwt_token(cls, header) -> dict:
        try:
            if not header or not header.startswith("Bearer "):
                return None

            token = header.split(" ")[1]
            user = jwt.decode(token, cls.JWT_SECRET, algorithms=[cls.JWT_ALGORITHM])
            
            if not isinstance(user, dict):
                return None

            if not user:
                return None

            return user
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
        except jwt.DecodeError:
            return None