# MED13 Authentication System - Product Requirements Document (PRD)

**Version:** 1.0
**Status:** Planning
**Owner:** Engineering Team
**Last Updated:** 2025-01-04

---

## Executive Summary

The Artana Resource Library requires a comprehensive, enterprise-grade authentication and authorization system to support multi-user access, role-based permissions, and security compliance for biomedical research data. This document outlines the complete implementation roadmap from basic JWT authentication to advanced security features.

---

## Table of Contents

1. [Goals & Objectives](#goals--objectives)
2. [Architecture Overview](#architecture-overview)
3. [Implementation Phases](#implementation-phases)
4. [Technical Specifications](#technical-specifications)
5. [Security Requirements](#security-requirements)
6. [Testing Strategy](#testing-strategy)
7. [Success Metrics](#success-metrics)
8. [Timeline & Resources](#timeline--resources)

---

## Goals & Objectives

### Primary Goals

1. **Secure User Authentication**: Implement JWT-based authentication with refresh token support
2. **Role-Based Authorization**: Support multiple user roles (Admin, Curator, Researcher, Viewer)
3. **Security Best Practices**: Implement industry-standard security measures (password hashing, rate limiting, audit logging)
4. **Scalable Architecture**: Build on Clean Architecture principles for maintainability and extensibility
5. **Comprehensive Testing**: Achieve 95%+ test coverage for security-critical components

### Success Criteria

- ✅ Zero security vulnerabilities in penetration testing
- ✅ Sub-500ms authentication response time
- ✅ 99.9% authentication service uptime
- ✅ Complete audit trail for all authentication events
- ✅ Seamless integration with existing FastAPI backend and Next.js frontend

---

## Architecture Overview

### Clean Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                       │
│  • FastAPI Auth Routes (/auth/login, /register, etc.)      │
│  • Next.js Auth Pages (login, register, profile)           │
│  • Authentication Middleware                                │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
│  • AuthenticationService (login, logout, token refresh)    │
│  • AuthorizationService (permission checking)              │
│  • UserManagementService (CRUD, profile updates)           │
│  • AuditLoggingService (security event tracking)           │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│                     Domain Layer                            │
│  • User Entity (with status, role, security fields)        │
│  • Session Entity (JWT token tracking)                     │
│  • Permission Value Objects (role-based permissions)       │
│  • Business Rules (password policy, account lockout)       │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│                 Infrastructure Layer                        │
│  • UserRepository (PostgreSQL persistence)                 │
│  • SessionRepository (session tracking)                    │
│  • JWTProvider (token creation/validation)                 │
│  • PasswordHasher (bcrypt with pre-hashing)                │
│  • AuditRepository (security event logging)                │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy, Pydantic v2
- **Authentication**: JWT (PyJWT), bcrypt (passlib)
- **Database**: PostgreSQL (production), SQLite (development)
- **Frontend**: Next.js 14, NextAuth.js, TypeScript
- **Testing**: Pytest, Jest, React Testing Library
- **Security**: Bandit, Safety, OWASP security practices

---

## Implementation Phases

### Phase 1: Core Authentication Foundation (Week 1-2)

**Objective**: Establish basic authentication infrastructure with secure user management

#### 1.1 Domain Layer Implementation

**Files to Create:**
- `src/domain/entities/user.py`
- `src/domain/entities/session.py`
- `src/domain/value_objects/permission.py`
- `src/domain/repositories/user_repository.py`
- `src/domain/repositories/session_repository.py`

**User Entity Specifications:**
```python
# Core fields
- id: UUID (primary key)
- email: EmailStr (unique, indexed)
- username: str (unique, indexed, 3-50 chars)
- full_name: str (1-100 chars)
- hashed_password: str (bcrypt hash)
- role: UserRole (enum: admin, curator, researcher, viewer)
- status: UserStatus (enum: active, inactive, suspended, pending_verification)

# Security fields
- email_verified: bool (default: False)
- email_verification_token: Optional[str]
- password_reset_token: Optional[str]
- password_reset_expires: Optional[datetime]
- last_login: Optional[datetime]
- login_attempts: int (default: 0)
- locked_until: Optional[datetime]

# Metadata
- created_at: datetime
- updated_at: datetime

# Business logic methods
- can_authenticate() -> bool
- is_locked() -> bool
- record_login_attempt(success: bool) -> None
```

**Session Entity Specifications:**
```python
- id: UUID
- user_id: UUID (foreign key)
- session_token: str (JWT access token)
- refresh_token: str (JWT refresh token)
- ip_address: Optional[str]
- user_agent: Optional[str]
- status: SessionStatus (active, expired, revoked)
- expires_at: datetime
- refresh_expires_at: datetime
- created_at: datetime
- last_activity: datetime

# Methods
- is_expired() -> bool
- is_refresh_expired() -> bool
- update_activity() -> None
- revoke() -> None
```

**Permission System:**
```python
# Permission enum
class Permission(str, Enum):
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    DATASOURCE_CREATE = "datasource:create"
    DATASOURCE_READ = "datasource:read"
    DATASOURCE_UPDATE = "datasource:update"
    DATASOURCE_DELETE = "datasource:delete"
    CURATION_REVIEW = "curation:review"
    CURATION_APPROVE = "curation:approve"
    SYSTEM_ADMIN = "system:admin"
    AUDIT_READ = "audit:read"

# Role-to-Permission mapping
class RolePermissions:
    @staticmethod
    def get_permissions_for_role(role: UserRole) -> List[Permission]
```

**Deliverables:**
- ✅ User and Session entities with full Pydantic validation
- ✅ Repository interfaces (abstract base classes)
- ✅ Permission value objects with role mappings
- ✅ 100% MyPy type safety compliance
- ✅ Unit tests for all domain entities (95%+ coverage)

---

#### 1.2 Infrastructure Layer Implementation

**Files to Create:**
- `src/infrastructure/security/password_hasher.py`
- `src/infrastructure/security/jwt_provider.py`
- `src/infrastructure/repositories/sqlalchemy_user_repository.py`
- `src/infrastructure/repositories/sqlalchemy_session_repository.py`
- `src/models/database/user.py` (SQLAlchemy model)
- `src/models/database/session.py` (SQLAlchemy model)

**Password Hasher Specifications:**
```python
class PasswordHasher:
    def __init__(self):
        # Use passlib with bcrypt (12 rounds)
        # Automatic pre-hashing for passwords > 72 bytes
        self.pwd_context = CryptContext(
            schemes=["bcrypt"],
            bcrypt__rounds=12,
            truncate_error=True
        )

    def hash_password(self, plain_password: str) -> str
    def verify_password(self, plain_password: str, hashed: str) -> bool
    def is_password_strong(self, password: str) -> bool
    def generate_secure_password(self, length: int = 16) -> str

    # Validation rules
    - Min length: 8 characters
    - Max length: 128 characters
    - Must contain: letter + number
```

**JWT Provider Specifications:**
```python
class JWTProvider:
    def __init__(self, secret_key: str, algorithm: str = "HS256")

    def create_access_token(
        self, user_id: UUID, role: UserRole,
        expires_delta: timedelta = 15 minutes
    ) -> str

    def create_refresh_token(
        self, user_id: UUID,
        expires_delta: timedelta = 7 days
    ) -> str

    def decode_token(self, token: str) -> Dict[str, Any]

    # Token payload structure
    {
        "sub": str(user_id),
        "role": role.value,
        "type": "access" | "refresh",
        "exp": expiration_timestamp,
        "iat": issued_at_timestamp
    }
```

**Database Models:**
```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    email_verification_token VARCHAR(255),
    password_reset_token VARCHAR(255),
    password_reset_expires TIMESTAMP,
    last_login TIMESTAMP,
    login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_status ON users(status);

-- Sessions table
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    status VARCHAR(20) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    refresh_expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP NOT NULL
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
```

**Deliverables:**
- ✅ Password hasher with truncation prevention
- ✅ JWT token provider with validation
- ✅ SQLAlchemy repositories with async support
- ✅ Database models with proper indexes
- ✅ Alembic migration for new tables
- ✅ Unit tests for security utilities (98%+ coverage)
- ✅ Integration tests for repositories

---

#### 1.3 Application Layer Implementation

**Files to Create:**
- `src/application/services/authentication_service.py`
- `src/application/services/authorization_service.py`
- `src/application/services/user_management_service.py`
- `src/application/dto/auth_requests.py`
- `src/application/dto/auth_responses.py`

**Authentication Service Specifications:**
```python
class AuthenticationService:
    def __init__(
        self,
        user_repository: UserRepository,
        session_repository: SessionRepository,
        jwt_provider: JWTProvider,
        password_hasher: PasswordHasher
    )

    async def authenticate_user(
        self,
        request: LoginRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> LoginResponse

    async def refresh_token(
        self, refresh_token: str
    ) -> LoginResponse

    async def logout(self, access_token: str) -> None

    async def verify_token(self, token: str) -> User

    # Security features
    - Timing attack resistance (constant-time validation)
    - Failed login attempt tracking
    - Account lockout after 5 failed attempts
    - Session creation with device fingerprinting
```

**Authorization Service Specifications:**
```python
class AuthorizationService:
    def __init__(self, user_repository: UserRepository)

    async def has_permission(
        self, user_id: UUID, permission: Permission
    ) -> bool

    async def get_user_permissions(
        self, user_id: UUID
    ) -> List[Permission]

    async def validate_role_hierarchy(
        self, requesting_user: User, target_user: User
    ) -> bool

    def check_resource_access(
        self, user: User, resource_id: UUID, action: str
    ) -> bool
```

**User Management Service Specifications:**
```python
class UserManagementService:
    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: PasswordHasher
    )

    async def register_user(
        self, request: RegisterUserRequest
    ) -> User

    async def update_user(
        self, user_id: UUID, request: UpdateUserRequest
    ) -> User

    async def change_password(
        self, user_id: UUID, old_password: str, new_password: str
    ) -> None

    async def request_password_reset(self, email: str) -> str

    async def reset_password(
        self, token: str, new_password: str
    ) -> None

    async def verify_email(self, token: str) -> None

    # User search and management
    async def list_users(
        self, skip: int = 0, limit: int = 100,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None
    ) -> List[User]

    async def get_user_statistics() -> Dict[str, Any]
```

**DTOs (Data Transfer Objects):**
```python
# Request DTOs
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterUserRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.VIEWER

class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None

# Response DTOs
class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic  # Exclude sensitive fields

class UserPublic(BaseModel):
    id: UUID
    email: EmailStr
    username: str
    full_name: str
    role: UserRole
    status: UserStatus
    email_verified: bool
    last_login: Optional[datetime]
    created_at: datetime
```

**Deliverables:**
- ✅ Authentication service with comprehensive security
- ✅ Authorization service with permission checking
- ✅ User management service with CRUD operations
- ✅ Request/response DTOs with validation
- ✅ Unit tests for all services (90%+ coverage)
- ✅ Integration tests for service orchestration

---

### Phase 2: API Integration & Middleware (Week 3)

**Objective**: Expose authentication via REST API and integrate with existing system

#### 2.1 FastAPI Routes Implementation

**Files to Create:**
- `src/routes/auth.py`
- `src/middleware/jwt_auth_middleware.py`
- `src/dependencies/auth_dependencies.py`

**Authentication Routes:**
```python
# src/routes/auth.py
router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/register", status_code=201)
async def register_user(request: RegisterUserRequest)

@router.post("/login")
async def login(request: LoginRequest, req: Request)

@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials)

@router.post("/refresh")
async def refresh_token(credentials: HTTPAuthorizationCredentials)

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest)

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest)

@router.post("/verify-email")
async def verify_email(token: str)

@router.get("/me")
async def get_current_user_profile(current_user: User = Depends(get_current_user))

@router.put("/me")
async def update_current_user_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user)
)

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user)
)
```

**Authentication Dependencies:**
```python
# src/dependencies/auth_dependencies.py

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
) -> User:
    """Extract and validate current authenticated user from JWT token."""
    # Decode JWT token
    # Verify session is active
    # Return User entity

async def require_permission(permission: Permission):
    """Dependency factory for permission-based access control."""
    async def permission_checker(
        current_user: User = Depends(get_current_user)
    ) -> User:
        # Check if user has required permission
        # Raise 403 if insufficient permissions
        return current_user
    return permission_checker

async def require_role(role: UserRole):
    """Dependency factory for role-based access control."""
    async def role_checker(
        current_user: User = Depends(get_current_user)
    ) -> User:
        # Check role hierarchy
        # Raise 403 if insufficient role level
        return current_user
    return role_checker
```

**JWT Authentication Middleware:**
```python
# src/middleware/jwt_auth_middleware.py

class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate JWT tokens for protected routes.

    Features:
    - Automatic token validation for protected endpoints
    - Session activity tracking
    - Excludes public routes (health, docs, auth endpoints)
    - Adds user info to request.state for downstream handlers
    """

    def __init__(
        self,
        app: Callable,
        auth_service: AuthenticationService,
        exclude_paths: List[str]
    )

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response
```

**Integration with Existing System:**
```python
# src/main.py updates

# Replace or supplement existing API key middleware
app.add_middleware(JWTAuthMiddleware,
    auth_service=get_auth_service(),
    exclude_paths=[
        "/health/",
        "/docs",
        "/openapi.json",
        "/auth/",
        "/"
    ]
)

# Update existing protected routes to use new auth
@router.get("/admin/users")
async def list_users(
    current_user: User = Depends(require_permission(Permission.USER_READ))
):
    # Route implementation

# Support both API key and JWT for backward compatibility (optional)
async def get_current_user_or_api_key(
    jwt_user: Optional[User] = Depends(get_current_user),
    api_key: Optional[str] = Depends(api_key_header)
) -> Union[User, str]:
    # Try JWT first, fall back to API key
    # Return user or API key identifier
```

**Deliverables:**
- ✅ Complete auth API endpoints with OpenAPI documentation
- ✅ JWT authentication middleware
- ✅ Reusable auth dependencies for route protection
- ✅ Integration with existing FastAPI app
- ✅ Backward compatibility option for API keys
- ✅ Integration tests for all endpoints (85%+ coverage)
- ✅ API documentation with examples

---

#### 2.2 Dependency Injection & Configuration

**Files to Update:**
- `src/infrastructure/dependency_injection/container.py`
- `src/config/settings.py`

**Dependency Container Updates:**
```python
# Add authentication services to container

class Container:
    # Security utilities
    @singleton
    def password_hasher(self) -> PasswordHasher:
        return PasswordHasher()

    @singleton
    def jwt_provider(self) -> JWTProvider:
        return JWTProvider(
            secret_key=self.config.jwt_secret_key,
            algorithm=self.config.jwt_algorithm
        )

    # Repositories
    @singleton
    def user_repository(self) -> UserRepository:
        return SqlAlchemyUserRepository(self.session_factory)

    @singleton
    def session_repository(self) -> SessionRepository:
        return SqlAlchemySessionRepository(self.session_factory)

    # Application services
    @singleton
    def authentication_service(self) -> AuthenticationService:
        return AuthenticationService(
            user_repository=self.user_repository(),
            session_repository=self.session_repository(),
            jwt_provider=self.jwt_provider(),
            password_hasher=self.password_hasher()
        )

    @singleton
    def authorization_service(self) -> AuthorizationService:
        return AuthorizationService(
            user_repository=self.user_repository()
        )

    @singleton
    def user_management_service(self) -> UserManagementService:
        return UserManagementService(
            user_repository=self.user_repository(),
            password_hasher=self.password_hasher()
        )
```

**Configuration Settings:**
```python
# src/config/settings.py

class Settings(BaseSettings):
    # Existing settings...

    # JWT Configuration
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=15, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    jwt_refresh_token_expire_days: int = Field(default=7, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS")

    # Password Policy
    password_min_length: int = Field(default=8, env="PASSWORD_MIN_LENGTH")
    password_max_length: int = Field(default=128, env="PASSWORD_MAX_LENGTH")
    password_require_uppercase: bool = Field(default=False, env="PASSWORD_REQUIRE_UPPERCASE")
    password_require_lowercase: bool = Field(default=True, env="PASSWORD_REQUIRE_LOWERCASE")
    password_require_digit: bool = Field(default=True, env="PASSWORD_REQUIRE_DIGIT")
    password_require_special: bool = Field(default=False, env="PASSWORD_REQUIRE_SPECIAL")

    # Account Security
    max_login_attempts: int = Field(default=5, env="MAX_LOGIN_ATTEMPTS")
    account_lockout_duration_minutes: int = Field(default=30, env="ACCOUNT_LOCKOUT_DURATION_MINUTES")
    max_concurrent_sessions: int = Field(default=5, env="MAX_CONCURRENT_SESSIONS")

    # Email Configuration (for password reset, email verification)
    smtp_host: str = Field(default="localhost", env="SMTP_HOST")
    smtp_port: int = Field(default=587, env="SMTP_PORT")
    smtp_username: Optional[str] = Field(default=None, env="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="noreply@med13foundation.org", env="SMTP_FROM_EMAIL")
```

**Environment Variables:**
```bash
# .env.example additions

# JWT Configuration (REQUIRED)
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Password Policy
PASSWORD_MIN_LENGTH=8
PASSWORD_MAX_LENGTH=128

# Account Security
MAX_LOGIN_ATTEMPTS=5
ACCOUNT_LOCKOUT_DURATION_MINUTES=30
MAX_CONCURRENT_SESSIONS=5

# Email Configuration (for production)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=your-sendgrid-api-key
SMTP_FROM_EMAIL=noreply@med13foundation.org
```

**Deliverables:**
- ✅ Dependency injection container with auth services
- ✅ Configuration settings with environment variables
- ✅ Secure defaults for all security settings
- ✅ Documentation for configuration options

---

### Phase 3: Frontend Integration (Week 4)

**Objective**: Integrate authentication with Next.js admin interface

#### 3.1 Next.js Authentication Setup

**Files to Create:**
- `src/web/lib/auth.ts` (NextAuth.js configuration)
- `src/web/app/auth/login/page.tsx`
- `src/web/app/auth/register/page.tsx`
- `src/web/app/auth/forgot-password/page.tsx`
- `src/web/components/auth/LoginForm.tsx`
- `src/web/components/auth/RegisterForm.tsx`
- `src/web/components/auth/ProtectedRoute.tsx`
- `src/web/middleware.ts` (route protection)
- `src/web/types/auth.ts`

**NextAuth.js Configuration:**
```typescript
// src/web/lib/auth.ts
import { NextAuthOptions } from "next-auth"
import CredentialsProvider from "next-auth/providers/credentials"

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" }
      },
      async authorize(credentials) {
        // Call FastAPI /auth/login endpoint
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(credentials),
        })

        if (!response.ok) return null

        const data = await response.json()

        return {
          id: data.user.id,
          email: data.user.email,
          name: data.user.full_name,
          role: data.user.role,
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
        }
      }
    })
  ],
  session: {
    strategy: "jwt",
    maxAge: 7 * 24 * 60 * 60, // 7 days
  },
  callbacks: {
    async jwt({ token, user, account }) {
      if (user) {
        token.accessToken = user.accessToken
        token.refreshToken = user.refreshToken
        token.role = user.role
      }
      return token
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken
      session.refreshToken = token.refreshToken
      session.user.role = token.role
      return session
    },
  },
  pages: {
    signIn: '/auth/login',
    error: '/auth/error',
  },
}
```

**Login Page:**
```typescript
// src/web/app/auth/login/page.tsx
export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl font-heading">
            Welcome to MED13 Admin
          </CardTitle>
          <CardDescription>
            Sign in to access your account
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LoginForm />
        </CardContent>
      </Card>
    </div>
  )
}
```

**Login Form Component:**
```typescript
// src/web/components/auth/LoginForm.tsx
'use client'

import { useState } from 'react'
import { signIn } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function LoginForm() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const result = await signIn('credentials', {
      email,
      password,
      redirect: false,
    })

    if (result?.error) {
      setError('Invalid email or password')
      setLoading(false)
    } else {
      router.push('/dashboard')
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </div>
      <div>
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      {error && (
        <div className="text-sm text-destructive">{error}</div>
      )}
      <Button type="submit" className="w-full" disabled={loading}>
        {loading ? 'Signing in...' : 'Sign In'}
      </Button>
    </form>
  )
}
```

**Route Protection Middleware:**
```typescript
// src/web/middleware.ts
import { withAuth } from "next-auth/middleware"

export default withAuth({
  callbacks: {
    authorized: ({ token, req }) => {
      // Protect admin routes
      if (req.nextUrl.pathname.startsWith("/admin")) {
        return token?.role === "admin"
      }

      // Protect curator routes
      if (req.nextUrl.pathname.startsWith("/curator")) {
        return token?.role === "admin" || token?.role === "curator"
      }

      // All other protected routes require authentication
      return !!token
    },
  },
  pages: {
    signIn: "/auth/login",
  },
})

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/admin/:path*",
    "/curator/:path*",
    "/profile/:path*",
  ]
}
```

**Deliverables:**
- ✅ NextAuth.js integration with FastAPI backend
- ✅ Login and registration pages with MED13 design system
- ✅ Protected route middleware
- ✅ Session management and token refresh
- ✅ Role-based route protection
- ✅ Error handling and loading states
- ✅ Component tests for auth UI (80%+ coverage)

---

#### 3.2 API Client & Type Safety

**Files to Create:**
- `src/web/lib/api-client.ts`
- `src/web/types/api.ts`
- `src/web/hooks/useAuth.ts`

**API Client:**
```typescript
// src/web/lib/api-client.ts
import { getSession } from 'next-auth/react'

class APIClient {
  private baseURL: string

  constructor() {
    this.baseURL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'
  }

  private async getHeaders(): Promise<HeadersInit> {
    const session = await getSession()

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }

    if (session?.accessToken) {
      headers['Authorization'] = `Bearer ${session.accessToken}`
    }

    return headers
  }

  async get<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseURL}${path}`, {
      method: 'GET',
      headers: await this.getHeaders(),
    })

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`)
    }

    return response.json()
  }

  async post<T>(path: string, data: any): Promise<T> {
    const response = await fetch(`${this.baseURL}${path}`, {
      method: 'POST',
      headers: await this.getHeaders(),
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`)
    }

    return response.json()
  }

  // Additional methods for PUT, DELETE, etc.
}

export const apiClient = new APIClient()
```

**Custom Auth Hook:**
```typescript
// src/web/hooks/useAuth.ts
import { useSession } from 'next-auth/react'

export function useAuth() {
  const { data: session, status } = useSession()

  return {
    user: session?.user,
    isAuthenticated: status === 'authenticated',
    isLoading: status === 'loading',
    role: session?.user?.role,
    hasPermission: (permission: string) => {
      // Check if user role has permission
      // Based on role hierarchy
    },
  }
}
```

**Deliverables:**
- ✅ Type-safe API client with authentication
- ✅ Custom React hooks for auth state
- ✅ Shared TypeScript types between frontend and backend
- ✅ Token refresh handling
- ✅ Hook tests (85%+ coverage)

---

### Phase 4: Advanced Security Features (Week 5)

**Objective**: Implement production-grade security enhancements

#### 4.1 Audit Logging

**Files to Create:**
- `src/domain/entities/audit_log.py`
- `src/infrastructure/repositories/audit_log_repository.py`
- `src/application/services/audit_logging_service.py`
- `src/models/database/audit_log.py`

**Audit Log Entity:**
```python
class AuditEvent(str, Enum):
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_REGISTER = "user_register"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_COMPLETE = "password_reset_complete"
    EMAIL_VERIFICATION = "email_verification"
    SESSION_CREATED = "session_created"
    SESSION_REVOKED = "session_revoked"
    PERMISSION_DENIED = "permission_denied"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"

class AuditLog(BaseModel):
    id: UUID
    event_type: AuditEvent
    user_id: Optional[UUID]
    ip_address: Optional[str]
    user_agent: Optional[str]
    success: bool
    details: Dict[str, Any]
    timestamp: datetime
    session_id: Optional[UUID]
```

**Audit Logging Service:**
```python
class AuditLoggingService:
    async def log_event(
        self,
        event_type: AuditEvent,
        user_id: Optional[UUID],
        ip_address: str,
        user_agent: str,
        success: bool,
        details: Dict[str, Any] = None
    ) -> None

    async def get_user_audit_trail(
        self, user_id: UUID, limit: int = 100
    ) -> List[AuditLog]

    async def detect_suspicious_activity(
        self, ip_address: str
    ) -> bool

    async def generate_compliance_report(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[str, Any]
```

**Database Table:**
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    success BOOLEAN NOT NULL,
    details JSONB,
    timestamp TIMESTAMP NOT NULL,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type);
CREATE INDEX idx_audit_logs_ip_address ON audit_logs(ip_address);
```

**Deliverables:**
- ✅ Complete audit logging infrastructure
- ✅ Automatic logging for all auth events
- ✅ Suspicious activity detection
- ✅ Compliance reporting capabilities
- ✅ Unit and integration tests (90%+ coverage)

---

#### 4.2 Rate Limiting & Brute Force Protection

**Files to Create:**
- `src/middleware/rate_limit_middleware.py`
- `src/infrastructure/security/rate_limiter.py`

**Rate Limiter:**
```python
class RateLimiter:
    def __init__(self, backend_client):
        self.backend = backend_client

    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        """Check if request is within rate limit."""
        # Sliding window rate limiting
        # Return True if allowed, False if exceeded

    async def record_failed_login(
        self, identifier: str
    ) -> int:
        """Record failed login attempt."""
        # Return total failed attempts in window

    async def is_ip_blocked(
        self, ip_address: str
    ) -> bool:
        """Check if IP is temporarily blocked."""
        # Check for brute force protection
```

**Rate Limit Middleware:**
```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    # Global rate limits
    - 100 requests per minute per IP
    - 1000 requests per hour per IP

    # Endpoint-specific limits
    - Login: 5 requests per minute per IP
    - Register: 3 requests per hour per IP
    - Password reset: 3 requests per hour per email

    async def dispatch(self, request: Request, call_next):
        # Check rate limits
        # Return 429 if exceeded
        # Add rate limit headers
```

**Deliverables:**
- ✅ Rate limiting
- ✅ IP-based brute force protection
- ✅ Endpoint-specific rate limits
- ✅ Automatic IP blocking for suspicious activity
- ✅ Rate limit tests (90%+ coverage)

---

#### 4.3 Email Verification & Password Reset

**Files to Create:**
- `src/infrastructure/email/email_service.py`
- `src/application/services/email_verification_service.py`
- `src/web/app/auth/verify-email/page.tsx`
- `src/web/app/auth/reset-password/page.tsx`

**Email Service:**
```python
class EmailService:
    def __init__(self, smtp_config: SMTPConfig)

    async def send_verification_email(
        self, user: User, token: str
    ) -> None
        """Send email verification link."""

    async def send_password_reset_email(
        self, user: User, token: str
    ) -> None
        """Send password reset link."""

    async def send_password_changed_notification(
        self, user: User
    ) -> None
        """Notify user of password change."""

    async def send_suspicious_activity_alert(
        self, user: User, details: Dict
    ) -> None
        """Alert user of suspicious login."""
```

**Email Verification Flow:**
```python
# User registration
1. User registers with email/password
2. Generate verification token (JWT with 24hr expiry)
3. Send verification email with link
4. User clicks link → verify token → activate account
5. Log event in audit trail

# Password reset flow
1. User requests password reset
2. Generate reset token (JWT with 1hr expiry)
3. Send reset email with link
4. User clicks link → validate token → set new password
5. Revoke all existing sessions
6. Send confirmation email
7. Log event in audit trail
```

**Deliverables:**
- ✅ Email service with SMTP integration
- ✅ Email verification workflow
- ✅ Password reset workflow
- ✅ HTML email templates with MED13 branding
- ✅ Next.js pages for email flows
- ✅ Unit and integration tests (85%+ coverage)

---

### Phase 5: Testing & Security Hardening (Week 6)

**Objective**: Achieve comprehensive test coverage and security validation

#### 5.1 Comprehensive Test Suite

**Test Structure:**
```
tests/
├── unit/
│   ├── domain/
│   │   ├── test_user_entity.py (95%+ coverage)
│   │   ├── test_session_entity.py (95%+ coverage)
│   │   └── test_permissions.py (100% coverage)
│   ├── infrastructure/
│   │   ├── test_password_hasher.py (98%+ coverage)
│   │   ├── test_jwt_provider.py (98%+ coverage)
│   │   └── test_repositories.py (90%+ coverage)
│   └── application/
│       ├── test_authentication_service.py (95%+ coverage)
│       ├── test_authorization_service.py (95%+ coverage)
│       └── test_user_management_service.py (90%+ coverage)
├── integration/
│   ├── test_auth_api_endpoints.py (90%+ coverage)
│   ├── test_database_integration.py (85%+ coverage)
│   └── test_middleware_integration.py (85%+ coverage)
├── security/
│   ├── test_timing_attacks.py
│   ├── test_sql_injection.py
│   ├── test_xss_prevention.py
│   ├── test_csrf_protection.py
│   └── test_rate_limiting.py
├── e2e/
│   ├── test_full_auth_flow.py
│   ├── test_password_reset_flow.py
│   └── test_multi_user_scenarios.py
└── performance/
    ├── test_auth_performance.py
    └── test_load_testing.py
```

**Key Test Scenarios:**

**Security Tests:**
- ✅ Password truncation prevention
- ✅ Timing attack resistance
- ✅ SQL injection prevention
- ✅ XSS prevention
- ✅ CSRF protection
- ✅ Brute force detection
- ✅ Session fixation prevention
- ✅ Token expiration validation

**Functional Tests:**
- ✅ User registration with validation
- ✅ Login with various scenarios (success, fail, locked)
- ✅ Token refresh flow
- ✅ Password reset complete flow
- ✅ Email verification flow
- ✅ Permission checking
- ✅ Role hierarchy validation
- ✅ Concurrent session management

**Performance Tests:**
- ✅ Login response time < 500ms
- ✅ Token validation < 10ms
- ✅ 100 concurrent logins without degradation
- ✅ Password hashing within acceptable time

**Deliverables:**
- ✅ 95%+ coverage for security-critical components
- ✅ 90%+ coverage for application services
- ✅ 85%+ overall coverage
- ✅ All security penetration tests passing
- ✅ Performance benchmarks met
- ✅ Zero security vulnerabilities in audit

---

#### 5.2 Security Audit & Penetration Testing

**Security Checklist:**

**Authentication Security:**
- ✅ Passwords hashed with bcrypt (12+ rounds)
- ✅ Long password truncation prevented
- ✅ JWT tokens properly signed and validated
- ✅ Token expiration enforced
- ✅ Refresh tokens properly rotated
- ✅ Sessions tracked and revocable
- ✅ Account lockout after failed attempts
- ✅ Timing attack resistance verified

**Authorization Security:**
- ✅ Role-based access control enforced
- ✅ Permission checks on all protected routes
- ✅ User can only access own resources
- ✅ Admin actions properly authorized
- ✅ Role hierarchy respected

**Infrastructure Security:**
- ✅ SQL injection prevention verified
- ✅ XSS prevention in all outputs
- ✅ CSRF tokens on state-changing operations
- ✅ Secure headers configured (HSTS, CSP, etc.)
- ✅ Rate limiting active
- ✅ CORS properly configured
- ✅ Secrets stored in environment variables
- ✅ Database connections encrypted

**Operational Security:**
- ✅ Audit logging complete
- ✅ Security events monitored
- ✅ Failed login alerts configured
- ✅ Suspicious activity detection active
- ✅ Session cleanup scheduled
- ✅ Token blacklist maintenance
- ✅ Regular security updates process

**Deliverables:**
- ✅ Security audit report
- ✅ Penetration test results
- ✅ Vulnerability assessment
- ✅ Security compliance checklist
- ✅ Remediation plan for any findings

---

### Phase 6: Production Deployment & Monitoring (Week 7)

**Objective**: Deploy to production with comprehensive monitoring

#### 6.1 Production Configuration

**Environment Setup:**
```bash
# Production environment variables
JWT_SECRET_KEY=<strong-random-key-64-chars>
DATABASE_URL=postgresql://user:pass@prod-db:5432/med13_prod
SMTP_HOST=smtp.sendgrid.net
SMTP_USERNAME=apikey
SMTP_PASSWORD=<sendgrid-api-key>

# Security settings
MAX_LOGIN_ATTEMPTS=5
ACCOUNT_LOCKOUT_DURATION_MINUTES=30
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
ALLOWED_ORIGINS=https://admin.med13foundation.org,https://curate.med13foundation.org
```

**Database Migration:**
```bash
# Run migrations in production
alembic upgrade head

# Create initial admin user
python scripts/create_admin_user.py \
  --email admin@med13foundation.org \
  --username admin \
  --full-name "MED13 Administrator"
```

**Docker Configuration Updates:**
```dockerfile
# Dockerfile additions for auth dependencies
RUN pip install passlib[bcrypt] PyJWT

# Health check for auth service
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8080/health/ || exit 1
```

**Cloud Run Deployment:**
```yaml
# Update cloudbuild.yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/med13-api:$COMMIT_SHA', '.']

  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/med13-api:$COMMIT_SHA']

  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'med13-api'
      - '--image=gcr.io/$PROJECT_ID/med13-api:$COMMIT_SHA'
      - '--region=us-central1'
      - '--platform=managed'
      - '--set-env-vars=JWT_SECRET_KEY=$$JWT_SECRET_KEY'
      - '--set-env-vars=DATABASE_URL=$$DATABASE_URL'
    secretEnv: ['JWT_SECRET_KEY', 'DATABASE_URL']

availableSecrets:
  secretManager:
    - versionName: projects/$PROJECT_ID/secrets/jwt-secret-key/versions/latest
      env: 'JWT_SECRET_KEY'
    - versionName: projects/$PROJECT_ID/secrets/database-url/versions/latest
      env: 'DATABASE_URL'
```

**Deliverables:**
- ✅ Production environment configuration
- ✅ Database migrations executed
- ✅ Initial admin user created
- ✅ Docker images updated and deployed
- ✅ Cloud Run services configured
- ✅ Secrets properly managed in Google Secret Manager

---

#### 6.2 Monitoring & Alerting

**Metrics to Monitor:**
```python
# Authentication metrics
- login_attempts_total (counter)
- login_failures_total (counter)
- login_success_total (counter)
- account_lockouts_total (counter)
- token_refreshes_total (counter)
- active_sessions_gauge (gauge)
- authentication_duration_seconds (histogram)

# Security metrics
- suspicious_activity_total (counter)
- rate_limit_exceeded_total (counter)
- permission_denied_total (counter)
- password_reset_requests_total (counter)

# Performance metrics
- jwt_token_validation_duration_seconds (histogram)
- password_hash_duration_seconds (histogram)
- database_query_duration_seconds (histogram)
```

**Alerting Rules:**
```yaml
# Critical alerts
- alert: HighFailedLoginRate
  expr: rate(login_failures_total[5m]) > 10
  annotations:
    summary: "High rate of failed login attempts"

- alert: SuspiciousActivityDetected
  expr: suspicious_activity_total > 0
  annotations:
    summary: "Suspicious authentication activity detected"

- alert: AuthenticationServiceDown
  expr: up{service="auth"} == 0
  annotations:
    summary: "Authentication service is down"

# Warning alerts
- alert: HighTokenRefreshRate
  expr: rate(token_refreshes_total[1h]) > 100
  annotations:
    summary: "Unusually high token refresh rate"

- alert: ManyAccountLockouts
  expr: rate(account_lockouts_total[1h]) > 5
  annotations:
    summary: "Multiple accounts being locked out"
```

**Logging Configuration:**
```python
# Structured logging for auth events
logger.info("User login successful", extra={
    "event": "user_login",
    "user_id": str(user.id),
    "ip_address": ip_address,
    "user_agent": user_agent,
    "timestamp": datetime.utcnow().isoformat()
})

logger.warning("Failed login attempt", extra={
    "event": "login_failed",
    "email": email,
    "ip_address": ip_address,
    "attempt_count": user.login_attempts,
    "timestamp": datetime.utcnow().isoformat()
})
```

**Deliverables:**
- ✅ Prometheus metrics instrumentation
- ✅ Grafana dashboards for auth metrics
- ✅ Alert rules configured
- ✅ Structured logging implemented
- ✅ Log aggregation (Stackdriver/CloudWatch)
- ✅ On-call runbook for auth incidents

---

## Technical Specifications

### Database Schema

**Complete ERD:**
```
┌─────────────────────────┐
│        users            │
├─────────────────────────┤
│ id (PK)                 │
│ email (UNIQUE)          │
│ username (UNIQUE)       │
│ full_name               │
│ hashed_password         │
│ role                    │
│ status                  │
│ email_verified          │
│ email_verification_token│
│ password_reset_token    │
│ password_reset_expires  │
│ last_login              │
│ login_attempts          │
│ locked_until            │
│ created_at              │
│ updated_at              │
└─────────────────────────┘
           │
           │ 1:N
           │
┌─────────────────────────┐
│       sessions          │
├─────────────────────────┤
│ id (PK)                 │
│ user_id (FK)            │
│ session_token           │
│ refresh_token           │
│ ip_address              │
│ user_agent              │
│ status                  │
│ expires_at              │
│ refresh_expires_at      │
│ created_at              │
│ last_activity           │
└─────────────────────────┘
           │
           │
           │
┌─────────────────────────┐
│      audit_logs         │
├─────────────────────────┤
│ id (PK)                 │
│ event_type              │
│ user_id (FK, nullable)  │
│ ip_address              │
│ user_agent              │
│ success                 │
│ details (JSONB)         │
│ timestamp               │
│ session_id (FK)         │
└─────────────────────────┘
```

### API Endpoints

**Complete API Surface:**

```
Authentication Endpoints:
POST   /auth/register              - Register new user
POST   /auth/login                 - Login with email/password
POST   /auth/logout                - Logout (revoke session)
POST   /auth/refresh               - Refresh access token
POST   /auth/forgot-password       - Request password reset
POST   /auth/reset-password        - Reset password with token
POST   /auth/verify-email          - Verify email with token
GET    /auth/me                    - Get current user profile
PUT    /auth/me                    - Update current user profile
POST   /auth/change-password       - Change password (authenticated)

User Management Endpoints (Admin only):
GET    /admin/users                - List all users
GET    /admin/users/{id}           - Get user by ID
POST   /admin/users                - Create user (admin)
PUT    /admin/users/{id}           - Update user
DELETE /admin/users/{id}           - Delete user
GET    /admin/users/{id}/sessions  - Get user's active sessions
DELETE /admin/users/{id}/sessions/{session_id} - Revoke specific session
GET    /admin/users/statistics     - Get user statistics

Audit Endpoints (Admin only):
GET    /admin/audit/logs           - Get audit logs (paginated)
GET    /admin/audit/users/{id}     - Get user audit trail
GET    /admin/audit/suspicious     - Get suspicious activity reports
GET    /admin/audit/report         - Generate compliance report
```

### Security Headers

**Required HTTP Headers:**
```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Content-Security-Policy: default-src 'self'; ...
```

---

## Security Requirements

### OWASP Top 10 Compliance

**A01:2021 – Broken Access Control:**
- ✅ Role-based access control enforced
- ✅ Permission checks on all protected routes
- ✅ User can only access own resources
- ✅ Admin actions properly authorized

**A02:2021 – Cryptographic Failures:**
- ✅ Passwords hashed with bcrypt (12+ rounds)
- ✅ JWT tokens properly signed (HS256)
- ✅ Sensitive data encrypted at rest
- ✅ TLS/HTTPS enforced in production

**A03:2021 – Injection:**
- ✅ SQLAlchemy parameterized queries
- ✅ Input validation with Pydantic
- ✅ Output encoding
- ✅ SQL injection tests passing

**A04:2021 – Insecure Design:**
- ✅ Security by design (Clean Architecture)
- ✅ Threat modeling completed
- ✅ Security patterns documented
- ✅ Rate limiting and throttling

**A05:2021 – Security Misconfiguration:**
- ✅ Secure defaults for all settings
- ✅ Secrets in environment variables
- ✅ Error messages don't leak info
- ✅ Security headers configured

**A06:2021 – Vulnerable Components:**
- ✅ Dependency scanning (Safety, Snyk)
- ✅ Regular updates process
- ✅ No known vulnerabilities
- ✅ SBOM maintained

**A07:2021 – Authentication Failures:**
- ✅ Strong password policy
- ✅ Account lockout mechanism
- ✅ Secure session management
- ✅ Multi-factor ready architecture

**A08:2021 – Data Integrity Failures:**
- ✅ JWT signature verification
- ✅ Input validation
- ✅ Audit logging
- ✅ Integrity checks

**A09:2021 – Logging Failures:**
- ✅ Comprehensive audit logging
- ✅ Security event monitoring
- ✅ Log aggregation
- ✅ Incident response plan

**A10:2021 – Server-Side Request Forgery:**
- ✅ URL validation
- ✅ Whitelist-based access
- ✅ Network segmentation
- ✅ Input sanitization

---

## Testing Strategy

### Coverage Targets

| Component | Target | Critical |
|-----------|--------|----------|
| Domain Entities | 95% | User, Session, Permission |
| Security Utils | 98% | PasswordHasher, JWTProvider |
| Application Services | 90% | Auth, User Management |
| Infrastructure | 85% | Repositories |
| API Routes | 85% | Auth endpoints |
| Frontend Components | 80% | Auth UI |
| **Overall** | **90%** | **Zero security gaps** |

### Test Types

**Unit Tests (70% of tests):**
- Domain entity validation
- Business logic correctness
- Security utility functions
- Service layer methods

**Integration Tests (20% of tests):**
- API endpoint flows
- Database operations
- Service orchestration
- Middleware integration

**Security Tests (5% of tests):**
- Penetration testing
- Vulnerability scanning
- Timing attack resistance
- SQL injection prevention

**E2E Tests (5% of tests):**
- Complete user flows
- Cross-browser testing
- Mobile responsiveness
- Real-world scenarios

---

## Success Metrics

### Performance Metrics

- **Login Response Time:** < 500ms (p95)
- **Token Validation:** < 10ms (p99)
- **Password Hashing:** 200-500ms (acceptable for security)
- **API Throughput:** > 100 requests/sec
- **Concurrent Users:** Support 1000+ simultaneous

### Security Metrics

- **Security Vulnerabilities:** 0 high/critical
- **Test Coverage:** 90%+ overall, 98%+ security-critical
- **Failed Penetration Tests:** 0
- **Unpatched Dependencies:** 0
- **Security Incidents:** 0 in first 30 days

### Operational Metrics

- **Uptime:** 99.9% authentication service availability
- **MTTR:** < 15 minutes for auth issues
- **Alert Response:** < 5 minutes for critical alerts
- **Deployment Frequency:** Weekly updates possible
- **Rollback Time:** < 5 minutes

### Business Metrics

- **User Adoption:** 80% of users migrate within 30 days
- **Support Tickets:** < 5% auth-related issues
- **User Satisfaction:** > 4.5/5 for auth experience
- **Feature Development:** No slowdown from auth integration

---

## Timeline & Resources

### Phase Timeline

| Phase | Duration | Key Deliverables | Risk Level |
|-------|----------|------------------|------------|
| Phase 1: Core Foundation | 2 weeks | Domain + Infrastructure + Application | Medium |
| Phase 2: API Integration | 1 week | FastAPI routes + Middleware | Low |
| Phase 3: Frontend | 1 week | Next.js auth pages + components | Low |
| Phase 4: Advanced Security | 1 week | Audit logging + Rate limiting + Email | Medium |
| Phase 5: Testing | 1 week | Comprehensive test suite + Security audit | High |
| Phase 6: Production | 1 week | Deployment + Monitoring + Documentation | High |
| **Total** | **7 weeks** | **Production-ready authentication** | **Medium** |

### Resource Requirements

**Development:**
- 1 Senior Backend Engineer (Python/FastAPI)
- 1 Senior Frontend Engineer (Next.js/TypeScript)
- 1 Security Engineer (part-time, review + audit)
- 1 DevOps Engineer (deployment + monitoring)

**Infrastructure:**
- PostgreSQL database (existing)
- SMTP service (SendGrid or similar)
- Monitoring tools (Prometheus + Grafana)

**External Services:**
- Email service ($10-50/month)
- Security scanning tools ($0-100/month)

---

## Risks & Mitigations

### Technical Risks

**Risk: JWT Token Compromise**
- Mitigation: Short-lived access tokens (15 min), refresh token rotation, session revocation
- Impact: High | Likelihood: Low

**Risk: Password Database Breach**
- Mitigation: Bcrypt with 12+ rounds, pre-hashing for long passwords, regular security audits
- Impact: Critical | Likelihood: Very Low

**Risk: Performance Degradation**
- Mitigation: Caching, database indexing, async operations, load testing
- Impact: Medium | Likelihood: Medium

**Risk: Migration Issues**
- Mitigation: Support both auth systems temporarily, gradual rollout, rollback plan
- Impact: High | Likelihood: Medium

### Operational Risks

**Risk: Production Deployment Failure**
- Mitigation: Staging environment testing, blue-green deployment, automated rollback
- Impact: High | Likelihood: Low

**Risk: Security Vulnerability Post-Launch**
- Mitigation: Regular security scanning, bug bounty program, incident response plan
- Impact: Critical | Likelihood: Low

**Risk: User Adoption Issues**
- Mitigation: Clear migration docs, support resources, gradual enforcement
- Impact: Medium | Likelihood: Low

---

## Appendices

### A. Security Checklist

**Pre-Launch Security Review:**
- [ ] All passwords hashed with bcrypt (12+ rounds)
- [ ] JWT tokens properly signed and validated
- [ ] All API endpoints protected
- [ ] Rate limiting active
- [ ] Audit logging complete
- [ ] HTTPS enforced
- [ ] Security headers configured
- [ ] Secrets in environment variables only
- [ ] SQL injection tests passing
- [ ] XSS prevention verified
- [ ] CSRF protection enabled
- [ ] Session management secure
- [ ] Account lockout working
- [ ] Password policy enforced
- [ ] Email verification working
- [ ] Password reset flow secure
- [ ] Penetration tests passed
- [ ] Security audit completed
- [ ] Incident response plan ready

### B. API Response Examples

**Successful Login:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "email": "user@example.com",
    "username": "researcher1",
    "full_name": "Dr. Jane Smith",
    "role": "researcher",
    "status": "active",
    "email_verified": true,
    "last_login": "2025-01-04T10:30:00Z",
    "created_at": "2024-12-01T08:00:00Z"
  }
}
```

**Failed Login:**
```json
{
  "detail": "Invalid email or password"
}
```

**Account Locked:**
```json
{
  "detail": "Account is locked due to multiple failed login attempts. Please try again in 30 minutes or reset your password."
}
```

### C. Environment Variables Reference

**Complete list of required and optional environment variables:**

```bash
# Required - JWT Configuration
JWT_SECRET_KEY=<strong-random-key>
JWT_ALGORITHM=HS256

# Optional - JWT Configuration
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Required - Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Optional - Email Configuration
SMTP_HOST=localhost
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=noreply@med13foundation.org

# Optional - Password Policy
PASSWORD_MIN_LENGTH=8
PASSWORD_MAX_LENGTH=128
PASSWORD_REQUIRE_UPPERCASE=false
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_DIGIT=true
PASSWORD_REQUIRE_SPECIAL=false

# Optional - Account Security
MAX_LOGIN_ATTEMPTS=5
ACCOUNT_LOCKOUT_DURATION_MINUTES=30
MAX_CONCURRENT_SESSIONS=5

# Optional - CORS
ALLOWED_ORIGINS=http://localhost:3000

# Optional - Monitoring
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=9090
```

---

## Document Control

**Version History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-04 | Engineering Team | Initial PRD creation |

**Approval:**

- [ ] Engineering Lead
- [ ] Security Team
- [ ] Product Owner
- [ ] DevOps Lead

**Next Review Date:** 2025-02-01

---

**End of Authentication System PRD**
