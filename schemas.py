from pydantic import BaseModel
from typing import Optional


# ---------------- ROLE SCHEMAS ----------------

class RoleCreate(BaseModel):

    name: str


class RoleResponse(BaseModel):

    id: int
    name: str

    class Config:
        from_attributes = True


# ---------------- USER SCHEMAS ----------------

class UserCreate(BaseModel):

    username: str
    email: str
    password: str
    role_id: int


class UserLogin(BaseModel):

    username: str
    password: str


class UserResponse(BaseModel):

    id: int
    username: str
    email: str
    role_id: int

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):

    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role_id: Optional[int] = None
    
# ---------------- MODULE SCHEMAS ----------------

class ModuleCreate(BaseModel):

    name: str


    # ---------------- ROLE-MODULE SCHEMAS ----------------

class RoleModuleCreate(BaseModel):

    role_id: int
    module_id: int
    
# ---------------- KNOWLEDGE BASE SCHEMAS ----------------

class KnowledgeBaseCreate(BaseModel):

    file_name: str
    source_type: str
    source_path: str