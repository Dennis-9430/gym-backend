"""Authentication router"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Optional
from app.auth.schemas import Token, UserResponse, UserCreate, PasswordChange
from app.auth.service import authenticate_user, create_token, get_user_by_username, initialize_default_users
from app.auth.utils import get_password_hash, decode_token
from app.auth.schemas import UserRole


router = APIRouter(prefix="/api/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserResponse:
    """Get current authenticated user from token"""
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    username: str = payload.get("sub")
    role: str = payload.get("role")
    
    if username is None or role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return UserResponse(username=username, role=UserRole(role))


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint"""
    user = await authenticate_user(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = await create_token(user.username, user.role)
    return token


@router.post("/logout")
async def logout(current_user: UserResponse = Depends(get_current_user)):
    """Logout endpoint"""
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    """Get current user info"""
    return current_user


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, current_user: UserResponse = Depends(get_current_user)):
    """Register new user (admin only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create users"
        )
    
    existing = await get_user_by_username(user_data.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    password_hash = get_password_hash(user_data.password)
    from app.auth.service import create_user
    new_user = await create_user(
        username=user_data.username,
        password_hash=password_hash,
        role=user_data.role,
        employee_id=user_data.employeeId
    )
    
    return UserResponse(
        username=new_user["username"],
        role=UserRole(new_user["role"]),
        employeeId=new_user.get("employeeId")
    )


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: UserResponse = Depends(get_current_user)
):
    """Change password"""
    from app.database import get_database, Collections
    
    user_doc = await get_user_by_username(current_user.username)
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    from app.auth.utils import verify_password
    if not verify_password(password_data.old_password, user_doc["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )
    
    new_hash = get_password_hash(password_data.new_password)
    db = get_database()
    await db[Collections.USERS].update_one(
        {"username": current_user.username},
        {"$set": {"password_hash": new_hash}}
    )
    
    return {"message": "Password changed successfully"}