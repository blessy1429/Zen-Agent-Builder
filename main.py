from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from models import APIUsage
from datetime import datetime
from fastapi.templating import Jinja2Templates
from fastapi import Form
from fastapi.responses import RedirectResponse
from slowapi import Limiter
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Header
from slowapi.errors import RateLimitExceeded
from models import WorkflowExecution
import bcrypt
from models import AgentExecution
from fastapi import BackgroundTasks
from models import LLMModel
from fastapi import UploadFile, File
import json
import os
import shutil
from datetime import datetime, timedelta
import uuid
from jose import JWTError, jwt
from pypdf import PdfReader
from fastapi.security import OAuth2PasswordBearer
from docx import Document
from database import SessionLocal, engine
import requests
from bs4 import BeautifulSoup
from models import Agent
from fastapi.staticfiles import StaticFiles
from models import (
    Base,
    User,
    Role,
    Module,
    RoleModule,
    KnowledgeBase,
    DocumentChunk,
    Agent,
    Workflow,
    WorkflowStep,
    LLMProvider,
    APIKey,
    AgentAPIToken,
    LLMModel,
    APIUsage,
    DocumentClassifier,
    AgentExecution,
    AgentExecution,
    WorkflowExecution
)

from schemas import (
    UserCreate,
    UserLogin,
    RoleCreate,
    ModuleCreate,
    RoleModuleCreate,
    KnowledgeBaseCreate
)

# Create Tables

Base.metadata.create_all(bind=engine)

# FastAPI App

app = FastAPI(
    title="Zen Agent Builder"
)
app.add_middleware(
    SessionMiddleware,
    secret_key="zen_agent_builder_secret_key"
)
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)
os.makedirs("uploads", exist_ok=True)
limiter = Limiter(
    key_func=get_remote_address
)

app.state.limiter = limiter

app.add_middleware(
    SlowAPIMiddleware
)
SECRET_KEY = "my_super_secret_key"

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 30
# Jinja Templates

templates = Jinja2Templates(
    directory="templates"
)

ALLOWED_IPS = [
    "127.0.0.1"
]
def get_db():

    db = SessionLocal()

    try:

        yield db

    finally:

        db.close()

def hash_password(password):

    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')


def verify_password(
    plain_password,
    hashed_password
):

    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login"
)
def create_access_token(
    data: dict,
    expires_delta: timedelta = None
):

    to_encode = data.copy()

    expire = datetime.utcnow() + (
        expires_delta or
        timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    to_encode.update(
        {"exp": expire}
    )

    encoded_jwt = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return encoded_jwt
def get_admin_context():
    return {
        "user_type": "Admin",
        "is_user": False
    }


def get_user_context(role_id):
    return {
        "user_type": "User",
        "is_user": True,
        "role_id": role_id
    }
def get_current_user(
    token: str = Depends(oauth2_scheme)
):

    credentials_exception = HTTPException(
        status_code=401,
        detail="Invalid token"
    )

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        username = payload.get("sub")

        if username is None:
            raise credentials_exception

        return username

    except JWTError:
        raise credentials_exception
    
def process_agent_execution(execution_id: int):

    db = SessionLocal()
    execution = None

    try:

        execution = db.query(
            AgentExecution
        ).filter(
            AgentExecution.id == execution_id
        ).first()

        if not execution:
            return

        execution.status = "Running"
        db.commit()

        output = generate_summary(
            execution.input_data or ""
        )

        execution.output_data = output

        execution.status = "Completed"
        execution.completed_at = datetime.utcnow()

        db.commit()

    except Exception as e:

        if execution:
            execution.status = "Failed"
            execution.output_data = str(e)
            db.commit()

    finally:
        db.close()
# Login Page Route

@app.get("/")
def login_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )
@app.get("/register-page")
def register_page(
    request: Request,
    db: Session = Depends(get_db)
):

   roles = db.query(Role).filter(
    Role.name != "Admin"
).all()

   return templates.TemplateResponse(
    request=request,
    name="register.html",
    context={
        "roles": roles
    }
)
@app.post("/register-form")
def register_form(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role_id: int = Form(...),
    db: Session = Depends(get_db)
):

    # Check Username
    existing_user = db.query(User).filter(
        User.username == username
    ).first()

    if existing_user:
        return {
            "message": "Username already exists"
        }

    # Check Email
    existing_email = db.query(User).filter(
        User.email == email
    ).first()

    if existing_email:
        return {
            "message": "Email already registered"
        }

    # Check Admin Restriction
    admin_role = db.query(Role).filter(
        Role.name == "Admin"
    ).first()

    if admin_role and role_id == admin_role.id:

        existing_admin = db.query(User).filter(
            User.role_id == admin_role.id
        ).first()

        if existing_admin:
            return {
                "message": "Only one Admin is allowed"
            }

    # Create User
    user = User(
    username=username,
     email=email,
     password=hash_password(password),
     role_id=role_id
 )

    db.add(user)
    db.commit()
    db.refresh(user)

    return RedirectResponse(
            url="/",
            status_code=303
        )
@app.post("/login-form")
@limiter.limit("5/minute")
def login_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(
        User.username == username
    ).first()

    if not user:
        return {
            "message": "Invalid Credentials"
        }

    if not verify_password(
        password,
        user.password
    ):
        return {
            "message": "Invalid Credentials"
        }

    if user.status == "Inactive":
        return {
            "message": "User account is disabled"
        }

    # Store session
    request.session["user_id"] = user.id

    request.session["username"] = user.username

    request.session["role_id"] = user.role_id

    request.session["role_name"] = user.role.name

    # Redirect
    if user.role.name == "Admin":

        return RedirectResponse(
            url="/dashboard",
            status_code=303
        )

    return RedirectResponse(
        url=f"/user-dashboard/{user.role_id}",
        status_code=303
    )
  
@app.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    if request.session.get("role_name") != "Admin":
        return RedirectResponse(
            "/",
            status_code=303
        )

    client_ip = request.client.host

    print("Client IP:", client_ip)

    if client_ip not in ALLOWED_IPS:
        raise HTTPException(
            status_code=403,
            detail="Access Denied"
        )

    # KPI Counts
    total_users = db.query(User).count()

    total_roles = db.query(Role).count()

    total_modules = db.query(Module).count()

    total_agents = db.query(Agent).count()

    total_workflows = db.query(
        Workflow
    ).count()

    total_knowledge_sources = db.query(
        KnowledgeBase
    ).count()

    total_chunks = db.query(
        DocumentChunk
    ).count()

    # Lists
    users = db.query(User).all()

    roles = db.query(Role).all()

    modules = db.query(Module).all()

    assigned_modules = db.query(
        RoleModule
    ).all()

    agents = db.query(Agent).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={

            # KPI Cards
            "total_users": total_users,

            "total_roles": total_roles,

            "total_modules": total_modules,

            "total_agents": total_agents,

            "total_workflows": total_workflows,

            "total_knowledge_sources":
                total_knowledge_sources,

                "total_chunks":
                    total_chunks,

                    # Tables
                    "users": users,

                    "roles": roles,

                    "modules": modules,

                    "agents": agents,

                    "assigned_modules":
                        assigned_modules,

                        **get_admin_context()
                    }
                )
    
@app.get("/user-dashboard/{role_id}")
def user_dashboard(
    role_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    if not request.session.get("user_id"):
      return RedirectResponse("/", status_code=303)

    mappings = db.query(RoleModule).filter(
        RoleModule.role_id == role_id
    ).all()

    module_ids = [
        mapping.module_id
        for mapping in mappings
    ]

    modules = db.query(Module).filter(
        Module.id.in_(module_ids)
    ).all()

    return templates.TemplateResponse(
    request=request,
    name="user_dashboard.html",
    context={
    "modules": modules,
    **get_user_context(role_id)
  }
)

    
@app.get("/delete-user/{user_id}")
def delete_user_page(
    user_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if user:
        db.delete(user)
        db.commit()

        return RedirectResponse(
            url="/dashboard",
            status_code=303
        )
@app.get("/edit-user/{user_id}")
def edit_user_page(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    if request.session.get("role_name") != "Admin":
     return RedirectResponse("/", status_code=303)

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    roles = db.query(Role).all()

    return templates.TemplateResponse(
    request=request,
    name="edit_user.html",
    context={
        "user": user,
        "roles": roles,
        **get_admin_context()
    }
)
    
@app.post("/update-user/{user_id}")
def update_user_form(
    user_id: int,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(""),
    role_id: int = Form(...),
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if not user:
        return {
            "message": "User Not Found"
        }

    # Check Duplicate Email
    existing_email = db.query(User).filter(
        User.email == email,
        User.id != user_id
    ).first()

    if existing_email:
        return {
            "message": "Email already registered"
        }

    # Check Duplicate Username
    existing_username = db.query(User).filter(
        User.username == username,
        User.id != user_id
    ).first()

    if existing_username:
        return {
            "message": "Username already exists"
        }

    # Only One Admin Allowed
    admin_role = db.query(Role).filter(
        Role.name == "Admin"
    ).first()

    if admin_role and role_id == admin_role.id:

        existing_admin = db.query(User).filter(
            User.role_id == admin_role.id,
            User.id != user_id
        ).first()

        if existing_admin:
            return {
                "message": "Only one Admin is allowed"
            }

        user.username = username
        user.email = email
        user.role_id = role_id

        # Update password only if user entered one
        if password:
            user.password = hash_password(password)

            db.commit()
            db.refresh(user)

            return RedirectResponse(
                url="/dashboard",
                status_code=303
            )
@app.get("/logout")
def logout(request: Request):

    request.session.clear()

    return RedirectResponse(
        url="/",
        status_code=303
    )
@app.get("/roles-page")
def roles_page(
    request: Request,
    db: Session = Depends(get_db)
):
    if request.session.get("role_name") != "Admin":
     return RedirectResponse("/", status_code=303)

    roles = db.query(Role).all()

    return templates.TemplateResponse(
    request=request,
    name="roles.html",
   context={
    "roles": roles,
    **get_admin_context()
}
)

@app.get("/security-test")
def security_test(
    request: Request
):

    return templates.TemplateResponse(
        request=request,
        name="security_test.html",
        context={
    **get_admin_context()
}
    )
   
@app.post("/roles")
def create_role(
    role: RoleCreate,
    db: Session = Depends(get_db)
):

    db_role = Role(
        name=role.name
    )

    db.add(db_role)

    db.commit()

    db.refresh(db_role)

    return db_role

@app.post("/modules")
def create_module(
    module: ModuleCreate,
    db: Session = Depends(get_db)
):

    existing_module = db.query(Module).filter(
        Module.name == module.name
    ).first()

    if existing_module:

        raise HTTPException(
            status_code=400,
            detail="Module already exists"
        )

    db_module = Module(
        name=module.name
    )

    db.add(db_module)
    db.commit()
    db.refresh(db_module)

    return db_module
@app.get("/modules")
def get_modules(
    db: Session = Depends(get_db)
):

    return db.query(Module).all()

@app.post("/role-modules")
def assign_module_to_role(
    role_module: RoleModuleCreate,
    db: Session = Depends(get_db)
):

    mapping = RoleModule(
        role_id=role_module.role_id,
        module_id=role_module.module_id
    )

    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    return mapping

@app.post("/knowledge-base")
def create_knowledge_base(
    kb: KnowledgeBaseCreate,
    db: Session = Depends(get_db)
):

    knowledge = KnowledgeBase(
    file_name=kb.file_name,
    source_type=kb.source_type,
    source_path=kb.source_path,
    status="Completed"
)

    db.add(knowledge)
    db.commit()
    db.refresh(knowledge)
    knowledge.status = "Completed"

    db.commit()

    return knowledge

@app.get("/knowledge-base")
def get_knowledge_base(
    db: Session = Depends(get_db)
):

    return db.query(KnowledgeBase).all()

@app.get("/role-modules")
def get_role_modules(
    db: Session = Depends(get_db)
):
    return db.query(RoleModule).all()

@app.get("/user-modules/{role_id}")
def get_user_modules(
    role_id: int,
    db: Session = Depends(get_db)
):

    mappings = db.query(RoleModule).filter(
        RoleModule.role_id == role_id
    ).all()

    module_ids = [
        mapping.module_id
        for mapping in mappings
    ]

    modules = db.query(Module).filter(
        Module.id.in_(module_ids)
    ).all()

    return modules
@app.post("/knowledge-base-form")
def knowledge_base_form(
    file_name: str = Form(...),
    source_type: str = Form(...),
    source_path: str = Form(...),
    db: Session = Depends(get_db)
):

    knowledge = KnowledgeBase(
    file_name=file_name,
    source_type=source_type,
    source_path=source_path,
    status="Completed"
)

    db.add(knowledge)
    db.commit()
    db.refresh(knowledge)

    return RedirectResponse(
        url="/knowledge-base-page",
        status_code=303
    )
@app.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    print("===== UPLOAD STARTED =====")

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file selected"
        )

    allowed_extensions = ["pdf", "docx", "txt"]

    extension = file.filename.split(".")[-1].lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, DOCX and TXT files are allowed"
        )

    print("Extension:", extension)

    file_path = f"uploads/{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    print("File Saved:", file_path)

    knowledge = KnowledgeBase(
            file_name=file.filename,
            source_type=extension.upper(),
            source_path=file_path,
            status="In Progress"
        )

    db.add(knowledge)
    db.commit()
    db.refresh(knowledge)

    try:

            # Extract Text
            if extension == "pdf":

                text = extract_pdf_text(
                    file_path
                )

            elif extension == "docx":

                text = extract_docx_text(
                    file_path
                )

            elif extension == "txt":

                text = extract_txt_text(
                    file_path
                )

            print("Text Length:", len(text))

                # Create Chunks
            chunks = chunk_text(text)

            print("Chunks Created:", len(chunks))

                # Store Chunks
            for chunk in chunks:

                    db_chunk = DocumentChunk(
                        knowledge_id=knowledge.id,
                        chunk_text=chunk
                    )

                    db.add(db_chunk)

            db.commit()

                    # Update Status
            knowledge.status = "Completed"

            db.commit()

            print("Inserted ID:", knowledge.id)
         
    except Exception as e:

            knowledge.status = "Failed"

            db.commit()

            print("Upload Error:", str(e))

    return RedirectResponse(
                url="/knowledge-base-page",
                status_code=303
            )
@app.get("/test-kb")
def test_kb(
    db: Session = Depends(get_db)
):
    return db.query(KnowledgeBase).all()

def extract_url_text(url):

    response = requests.get(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0"
            }
        )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    return soup.get_text(
        separator=" ",
        strip=True
    )

@app.post("/add-url")
def add_url(
    url: str = Form(...),
    db: Session = Depends(get_db)
):

    knowledge = KnowledgeBase(
        file_name="Website URL",
        source_type="URL",
        source_path=url,
        status="In Progress"
    )

    db.add(knowledge)
    db.commit()
    db.refresh(knowledge)

    try:

        print("URL Processing Started")

        text = extract_url_text(url)

        print("Extracted Text:")
        print(text[:500])

        chunks = chunk_text(text)

        print("Chunks Created:", len(chunks))

        # Save all chunks
        for chunk in chunks:

            db_chunk = DocumentChunk(
                knowledge_id=knowledge.id,
                chunk_text=chunk
            )

            db.add(db_chunk)

            # Commit once after all chunks
        db.commit()

            # Update status after successful processing
        knowledge.status = "Completed"

        db.commit()

        print("Knowledge Base Completed")

    except Exception as e:

        knowledge.status = "Failed"

        db.commit()

        print("URL Error:", str(e))

    return RedirectResponse(
            url="/knowledge-base-page",
            status_code=303
        )
@app.get("/modules-page")
def modules_page(
    request: Request,
    db: Session = Depends(get_db)
):
    if request.session.get("role_name") != "Admin":
     return RedirectResponse("/", status_code=303)

    modules = db.query(Module).all()

    return templates.TemplateResponse(
    request=request,
    name="modules.html",
    context={
    "modules": modules,
    **get_admin_context()
}
)
    
@app.get("/knowledge-base-page")
def knowledge_base_page(
    request: Request,
    db: Session = Depends(get_db)
):

    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    records = db.query(KnowledgeBase).all()

    chunk_counts = {}

    for record in records:
        count = db.query(DocumentChunk).filter(
            DocumentChunk.knowledge_id == record.id
        ).count()

        chunk_counts[record.id] = count

    role_name = request.session.get("role_name")
    role_id = request.session.get("role_id")

    context = {
        "records": records,
        "chunk_counts": chunk_counts,
    }

    if role_name == "Admin":
        context.update(get_admin_context())
    else:
        context.update(get_user_context(role_id))

    return templates.TemplateResponse(
        request=request,
        name="knowledge_base.html",
        context=context,
    )
    
@app.get("/delete-knowledge/{knowledge_id}")
def delete_knowledge(
    knowledge_id: int,
    db: Session = Depends(get_db)
):

    record = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == knowledge_id
    ).first()

    if record:
        db.delete(record)
        db.commit()
    return RedirectResponse(
            url="/knowledge-base-page",
            status_code=303
        )
    
@app.post("/register")
def register(
    user: UserCreate,
    db: Session = Depends(get_db)
):

    # Check Username
    existing_user = db.query(User).filter(
        User.username == user.username
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username already exists"
        )

    # Check Email
    existing_email = db.query(User).filter(
        User.email == user.email
    ).first()

    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Check Admin Restriction
    admin_role = db.query(Role).filter(
        Role.name == "Admin"
    ).first()

    if admin_role and user.role_id == admin_role.id:

        existing_admin = db.query(User).filter(
            User.role_id == admin_role.id
        ).first()

        if existing_admin:
            raise HTTPException(
                status_code=400,
                detail="Only one Admin is allowed"
            )

    # Create User
    db_user = User(
    username=user.username,
    email=user.email,
    password=hash_password(user.password),
    role_id=user.role_id
 )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user
    
@app.post("/login")
def login(
    user: UserLogin,
    db: Session = Depends(get_db)
):

    db_user = db.query(User).filter(
        User.username == user.username
    ).first()

    if not db_user:

        raise HTTPException(
            status_code=401,
            detail="Invalid Credentials"
        )
    if not verify_password(
    user.password,
    db_user.password
):

      raise HTTPException(
        status_code=401,
        detail="Invalid Credentials"
    )

    access_token = create_access_token(
    data={
        "sub": db_user.username
    }
)

    return {
    "access_token": access_token,
    "token_type": "bearer",
    "username": db_user.username,
    "role": db_user.role.name
}
    
@app.get("/users")
def get_users(
    db: Session = Depends(get_db)
):

    return db.query(User).all()
@app.get("/profile")
def profile(
    current_user: str = Depends(get_current_user)
):
    return {
        "message": f"Welcome {current_user}"
    }
@app.get("/roles")
def get_roles(
    db: Session = Depends(get_db)
):

    return db.query(Role).all()

@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User Not Found"
        )

    db.delete(user)

    db.commit()

    return {
        "message": "User Deleted Successfully"
    }
    
@app.put("/users/{user_id}")
def update_user(
    user_id: int,
    user_data: UserCreate,
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User Not Found"
        )

    # Check Email
    existing_email = db.query(User).filter(
        User.email == user_data.email,
        User.id != user_id
    ).first()

    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Check Username
    existing_username = db.query(User).filter(
        User.username == user_data.username,
        User.id != user_id
    ).first()

    if existing_username:
        raise HTTPException(
            status_code=400,
            detail="Username already exists"
        )

    user.username = user_data.username
    user.email = user_data.email
    user.password = hash_password(
        user_data.password
    )
    user.role_id = user_data.role_id

    db.commit()
    db.refresh(user)

    return {
        "message": "User Updated Successfully"
    }
    
@app.delete("/roles/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db)
):

    role = db.query(Role).filter(
        Role.id == role_id
    ).first()

    if not role:
        raise HTTPException(
            status_code=404,
            detail="Role Not Found"
        )

    if role.name in ["Admin", "User"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete Admin or User role"
        )

    db.query(RoleModule).filter(
        RoleModule.role_id == role_id
    ).delete()

    db.delete(role)

    db.commit()

    return {
        "message": "Role deleted successfully"
    }

def chunk_text(
    text,
    chunk_size=500,
    overlap=50
):

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunks.append(
            text[start:end]
        )

        start += (
            chunk_size - overlap
        )
    return chunks
    
def extract_pdf_text(
    file_path
):

    text = ""

    pdf = PdfReader(
        file_path
    )

    for page in pdf.pages:

        text += (
            page.extract_text()
            or ""
        )

    return text

def extract_docx_text(
    file_path
):

    doc = Document(
        file_path
    )

    text = ""

    for para in doc.paragraphs:

        text += (
            para.text + "\n"
        )
    return text

def extract_txt_text(
    file_path
):

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        return file.read()
    
@app.get("/delete-module/{module_id}")
def delete_module(
    module_id: int,
    db: Session = Depends(get_db)
):

    module = db.query(Module).filter(
        Module.id == module_id
    ).first()

    if module:

        db.query(RoleModule).filter(
            RoleModule.module_id == module_id
        ).delete()

        db.delete(module)

        db.commit()

    return RedirectResponse(
         url="/dashboard",
        status_code=303
     )
@app.get("/document-chunks")
def get_document_chunks(
    db: Session = Depends(get_db)
):

    return db.query(
        DocumentChunk
    ).all()
    
@app.get("/chat-page")
def chat_page(
    request: Request,
    db: Session = Depends(get_db)
):

    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    agents = db.query(Agent).all()

    role_name = request.session.get("role_name")
    role_id = request.session.get("role_id")

    context = {
        "agents": agents
    }

    if role_name == "Admin":
        context.update(get_admin_context())
    else:
        context.update(get_user_context(role_id))

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context=context
        )
@app.post("/chat")
def chat(
    request: Request,
    agent_id: int = Form(...),
    question: str = Form(...),
    db: Session = Depends(get_db)
):

    if not request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    # Get selected agent
    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    if not agent:

        return templates.TemplateResponse(
            request=request,
            name="chat.html",
            context={
                "question": question,
                "answer": "Agent not found",
                "agents": db.query(Agent).all()
            }
        )

    # Get assigned Knowledge Base
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.file_name ==
        agent.knowledge_base_name
    ).first()

    if not kb:

        return templates.TemplateResponse(
            request=request,
            name="chat.html",
            context={
                "question": question,
                "answer": "Knowledge Base not assigned",
                "agents": db.query(Agent).all()
            }
        )

    # Retrieve chunks
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.knowledge_id == kb.id
    ).all()

    stop_words = {
        "what", "is", "the",
        "a", "an", "of",
        "to", "in", "for",
        "on", "and", "are"
    }

    words = [
        word
        for word in question.lower().split()
        if word not in stop_words
    ]

    best_chunk = None
    best_score = 0

    for chunk in chunks:

        chunk_text = chunk.chunk_text.lower()

        score = 0

        for word in words:

            if word in chunk_text:
                score += 1

        if score > best_score:
           best_score = score
           best_chunk = chunk.chunk_text

    if best_chunk:

         answer = generate_concise_answer(
             question,
             best_chunk
         )

    else:

        answer = "No answer found"

    role_name = request.session.get("role_name")
    role_id = request.session.get("role_id")

    context = {
       "question": question,
        "answer": answer,
        "agents": db.query(Agent).all(),
         "selected_agent": agent.agent_name,
         "selected_kb": agent.knowledge_base_name
    }

    if role_name == "Admin":
       context.update(get_admin_context())
    else:
       context.update(get_user_context(role_id))

    return templates.TemplateResponse(
         request=request,
         name="chat.html",
         context=context
     )

@app.get("/check-db")
def check_db(db: Session = Depends(get_db)):
    return {
        "users": db.query(User).count(),
        "roles": db.query(Role).count(),
        "modules": db.query(Module).count(),
        "knowledge_base": db.query(KnowledgeBase).count(),
        "chunks": db.query(DocumentChunk).count()
    }
    
@app.get("/seed")
def seed(db: Session = Depends(get_db)):

    admin_role = db.query(Role).filter(
        Role.name == "Admin"
    ).first()

    if not admin_role:
        db.add(Role(name="Admin"))

        user_role = db.query(Role).filter(
            Role.name == "User"
        ).first()

        if not user_role:
            db.add(Role(name="User"))

            db.commit()

            module_names = [
                "Knowledge Base",
                "Agent Chat",
                "Agent Builder",
                "Workflow Builder"
            ]

            for module_name in module_names:

                existing_module = db.query(Module).filter(
                    Module.name == module_name
                ).first()

                if not existing_module:
                    db.add(
                        Module(name=module_name)
                    )

                    db.commit()

                    return {
                        "message": "Default data added successfully"
                    }
@app.get("/show-modules")
def show_modules(db: Session = Depends(get_db)):
    modules = db.query(Module).all()

    return [
        {
            "id": m.id,
            "name": m.name
        }
        for m in modules
    ]

@app.get("/add-default-modules")
def add_default_modules(
    db: Session = Depends(get_db)
):
    module_names = [
    "Knowledge Base",
    "Agent Chat",
    "Agent Builder",
    "Workflow Builder"
]

    for name in module_names:

        existing = db.query(Module).filter(
            Module.name == name
        ).first()

        if not existing:
            db.add(
                Module(name=name)
            )

            db.commit()

    return {
    "message": "Modules added successfully"
  }

@app.get("/db-path")
def db_path():
    import os

    return {
         "cwd": os.getcwd(),
         "users_db_exists": os.path.exists("users.db")
       }
@app.post("/add-role-form")
def add_role_form(
    role_name: str = Form(...),
    db: Session = Depends(get_db)
):
    db.add(Role(name=role_name))
    db.commit()

    return RedirectResponse(
        url="/dashboard",
        status_code=303
    )
    
@app.post("/add-module-form")
def add_module_form(
    module_name: str = Form(...),
    db: Session = Depends(get_db)
):
    db.add(Module(name=module_name))
    db.commit()

    return RedirectResponse(
        url="/dashboard",
        status_code=303
    )
@app.post("/assign-module")
def assign_module(
    role_id: int = Form(...),
    module_id: int = Form(...),
    db: Session = Depends(get_db)
):
    mapping = RoleModule(
        role_id=role_id,
        module_id=module_id
    )

    db.add(mapping)
    db.commit()

    return RedirectResponse(
        url="/dashboard",
        status_code=303
    )
@app.get("/test-agents")
def test_agents(
    db: Session = Depends(get_db)
):
    return db.query(Agent).all()
@app.get("/agent-builder")
def agent_builder(
    request: Request,
    db: Session = Depends(get_db)
):
    if request.session.get("role_name") != "Admin":
        return RedirectResponse(
            "/",
            status_code=303
        )

    agents = db.query(Agent).all()

    knowledge_bases = db.query(
        KnowledgeBase
    ).all()

    providers = db.query(
        LLMProvider
    ).all()

    api_keys = db.query(
        APIKey
    ).all()

    models = db.query(
        LLMModel
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="agent_builder.html",
        context={
            "agents": agents,
            "knowledge_bases": knowledge_bases,
            "providers": providers,
            "api_keys": api_keys,
            "models": models,
            **get_admin_context()
        }
    )
@app.post("/create-agent")
def create_agent(
    agent_name: str = Form(...),
    prompt: str = Form(...),
    input_type: str = Form(...),
    output_type: str = Form(...),
    description: str = Form(""),
    knowledge_base_name: str = Form(""),
    provider_id: int = Form(None),
    model_id: int = Form(None),
    api_key_id: int = Form(None),
    is_published: str = Form(None),
    agent_category: str = Form(...),
    processing_mode: str = Form(...),
    status: str = Form("Active"),
    db: Session = Depends(get_db)
):

    model_name = ""

    if model_id:
        model = db.query(
            LLMModel
        ).filter(
            LLMModel.id == model_id
        ).first()

        if model:
            model_name = model.model_name
    agent = Agent(
    agent_name=agent_name,
    agent_category=agent_category,
    prompt=prompt,
    input_type=input_type,
    output_type=output_type,
    processing_mode=processing_mode,
    knowledge_base_name=knowledge_base_name,
    status=status,
    provider_id=provider_id,
    model_id=model_id,
    model_name=model_name,
    api_key_id=api_key_id,
    is_published=bool(is_published),
    api_endpoint=(
        f"/api/agents/{agent_name.lower().replace(' ', '-')}"
        if is_published
        else None
    )
)
    db.add(agent)

    db.commit()

    db.refresh(agent)

    return RedirectResponse(
                url="/agent-builder",
                status_code=303
            )
@app.get("/delete-agent/{agent_id}")
def delete_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):
    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    if agent:
        db.delete(agent)
        db.commit()

        return RedirectResponse(
            "/agent-builder",
            status_code=303
        )

@app.get("/toggle-module/{module_id}")
def toggle_module(
    module_id: int,
    db: Session = Depends(get_db)
):

    module = db.query(Module).filter(
        Module.id == module_id
    ).first()

    if module:

        if module.status == "Active":

            module.status = "Inactive"

        else:

            module.status = "Active"

        db.commit()

    return RedirectResponse(
         url="/modules-page",
        status_code=303
 )
@app.get("/edit-module/{module_id}")
def edit_module_page(
    module_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    if request.session.get("role_name") != "Admin":
     return RedirectResponse("/", status_code=303)

    module = db.query(Module).filter(
        Module.id == module_id
    ).first()

    return templates.TemplateResponse(
        request=request,
        name="edit_module.html",
        context={
    "module": module,
    **get_admin_context()
    }
 )
@app.post("/update-module/{module_id}")
def update_module(
    module_id: int,
    module_name: str = Form(...),
    db: Session = Depends(get_db)
):

    module = db.query(Module).filter(
        Module.id == module_id
    ).first()

    if module:

        module.name = module_name

        db.commit()

        return RedirectResponse(
            url="/modules-page",
            status_code=303
        )
        
@app.get("/toggle-role/{role_id}")
def toggle_role(
    role_id: int,
    db: Session = Depends(get_db)
):

    role = db.query(Role).filter(
        Role.id == role_id
    ).first()

    if not role:
        raise HTTPException(
            status_code=404,
            detail="Role Not Found"
        )

    if role.name in ["Admin", "User"]:
        return RedirectResponse(
            url="/roles-page",
            status_code=303
        )

    if role.status == "Active":

        role.status = "Inactive"

    else:

        role.status = "Active"

    db.commit()

    return RedirectResponse(
            url="/roles-page",
            status_code=303
        )
@app.get("/edit-role/{role_id}")
def edit_role_page(
    role_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    if request.session.get("role_name") != "Admin":
     return RedirectResponse("/", status_code=303)

    role = db.query(Role).filter(
        Role.id == role_id
    ).first()

    return templates.TemplateResponse(
        request=request,
        name="edit_role.html",
        context={
    "role": role,
    **get_admin_context()
  }
    )
    
    
@app.post("/update-role/{role_id}")
def update_role(
    role_id: int,
    role_name: str = Form(...),
    db: Session = Depends(get_db)
):

    role = db.query(Role).filter(
        Role.id == role_id
    ).first()

    if not role:

        raise HTTPException(
            status_code=404,
            detail="Role Not Found"
        )

    role.name = role_name

    db.commit()

    return RedirectResponse(
        url="/roles-page",
        status_code=303
    )
    
@app.get("/toggle-user/{user_id}")
def toggle_user(
    user_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User Not Found"
        )

    if user.status == "Active":

        user.status = "Inactive"

    else:

        user.status = "Active"

    db.commit()

    return RedirectResponse(
            url="/dashboard",
            status_code=303
        )
def generate_concise_answer(question, text):
    question = question.lower()

    lines = text.split("\n")

    if "name" in question:
        for line in lines:
            if "name:" in line.lower():
                return line.split(":", 1)[1].strip()

    if "employee id" in question or "id" in question:
        for line in lines:
             if "employee id:" in line.lower():
                 return line.split(":", 1)[1].strip()

    if "role" in question:
        for line in lines:
         if "role:" in line.lower():
            return line.split(":", 1)[1].strip()

    if "organization" in question:
        for line in lines:
         if "organization:" in line.lower():
            return line.split(":", 1)[1].strip()

    if "department" in question:
        for line in lines:
         if "department:" in line.lower():
             return line.split(":", 1)[1].strip()

    if "skills" in question:
        skills = []
        capture = False

        for line in lines:

            if "skills" in line.lower():
                capture = True
                continue

            if capture:

               if line.strip().startswith("-"):
                  skills.append(
                    line.strip()
                    .replace("-", "")
                    .strip()
              )
            elif line.strip():
                break

        if skills:
            return ", ".join(skills)

    return "Answer found in document but could not extract a concise response."

def generate_summary(text):

    lines = text.split("\n")

    lines = [
        line.strip()
        for line in lines
        if line.strip()
    ]

    summary = "\n".join(
        lines[:8]
    )

    return summary

@app.get("/execute-agent/{agent_id}")
def execute_agent_page(
    agent_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    return templates.TemplateResponse(
        request=request,
        name="execute_agent.html",
        context={
    "agent": agent,
    **get_admin_context()
}
    )
    
@app.post("/run-agent/{agent_id}")
async def run_agent(

    agent_id: int,

    request: Request,

    file: UploadFile = File(...),

    db: Session = Depends(get_db)

):

    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    if not agent:

        raise HTTPException(
            status_code=404,
            detail="Agent not found"
        )

    file_path = f"uploads/{file.filename}"

    with open(file_path, "wb") as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    extension = file.filename.split(".")[-1].lower()

    if extension == "pdf":

            text = extract_pdf_text(
                file_path
            )

    elif extension == "docx":

            text = extract_docx_text(
                file_path
            )

    elif extension == "txt":

            text = extract_txt_text(
                file_path
            )

    else:

         text = "Unsupported File Type"

    # Always initialize output
    output = text

    print("Output Type:", agent.output_type)
    if agent.output_type == "Summary":
        output = generate_summary(text)
    elif agent.output_type == "JSON":
        output = extract_json(text)
    elif agent.output_type == "Text":
        output = text

    return templates.TemplateResponse(
        request=request,
        name="execute_agent.html",
        context={
            "agent": agent,
            "output": output,
            **get_admin_context()
        }
    )


def extract_json(text):

    data = {}

    lines = text.split("\n")

    for line in lines:

        if ":" in line:

            key, value = line.split(":", 1)

            key = key.strip() \
            .lower() \
            .replace(" ", "_")

            data[key] = value.strip()

    return json.dumps(
                data,
                indent=4
            )
            
def text_to_sql(text):

    text = text.lower()

    if "active users" in text:

        return """
        SELECT *
        FROM users
        WHERE status='Active';
        """

    elif "inactive users" in text:

        return """
        SELECT *
        FROM users
        WHERE status='Inactive';
        """

    elif "all users" in text:

        return """
        SELECT *
        FROM users;
        """

    elif "all roles" in text:

        return """
        SELECT *
        FROM roles;
        """

    elif "all modules" in text:

        return """
        SELECT *
        FROM modules;
        """

    return "Unable to generate SQL"

@app.get("/execute-text-sql/{agent_id}")
def execute_text_sql(

    request: Request,

    agent_id: int,

    db: Session = Depends(get_db)

):

    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    return templates.TemplateResponse(
        request=request,
        name="execute_text_sql.html",
        context={
    "agent": agent,
    **get_admin_context()
}
    )
    
@app.post("/run-text-sql/{agent_id}")
def run_text_sql(

    request: Request,

    agent_id: int,

    question: str = Form(...),

    db: Session = Depends(get_db)

):

    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    output = text_to_sql(
        question
    )
   
    return templates.TemplateResponse(
    request=request,
    name="execute_text_sql.html",
    context={
    "agent": agent,
    "output": output,
   **get_admin_context()
}
)
    
@app.get("/delete-admin")
def delete_admin(
    db: Session = Depends(get_db)
):
    admin_role = db.query(Role).filter(
        Role.name == "Admin"
    ).first()

    if not admin_role:
        return {
            "message": "Admin role not found"
        }

    admin_user = db.query(User).filter(
        User.role_id == admin_role.id
    ).first()

    if not admin_user:
        return {
            "message": "No admin found"
        }

    db.delete(admin_user)
    db.commit()

    return {
        "message": "Admin deleted successfully"
    }
@app.get("/create-admin")
def create_admin(
    db: Session = Depends(get_db)
):

    admin_role = db.query(Role).filter(
        Role.name == "Admin"
    ).first()

    if not admin_role:
        return {
            "message": "Admin role not found"
        }

    existing_admin = db.query(User).filter(
        User.email == "admin@gmail.com"
    ).first()

    if existing_admin:
        return {
            "message": "Admin already exists"
        }

    admin = User(
        username="admin",
        email="admin@gmail.com",
        password=hash_password("admin123"),
        role_id=admin_role.id,
        status="Active"
    )

    db.add(admin)
    db.commit()

    return {
        "message": "Admin Created Successfully"
    }
@app.get("/delete-role-module/{assignment_id}")
def delete_role_module(
    assignment_id: int,
    db: Session = Depends(get_db)
):

    assignment = db.query(
        RoleModule
    ).filter(
        RoleModule.id == assignment_id
    ).first()

    if assignment:

        db.delete(assignment)

        db.commit()

        return RedirectResponse(
            url="/dashboard",
            status_code=303
        )
        
@app.get("/edit-agent/{agent_id}")
def edit_agent(
    request: Request,
    agent_id: int,
    db: Session = Depends(get_db)
):
    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    return templates.TemplateResponse(
    request=request,
    name="edit_agent.html",
    context={
        "agent": agent,
        **get_admin_context()
    }
)
    
@app.post("/update-agent/{agent_id}")
def update_agent(
    agent_id: int,
    agent_name: str = Form(...),
    prompt: str = Form(...),
    input_type: str = Form(...),
    output_type: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db)
):

    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    agent.agent_name = agent_name
    agent.prompt = prompt
    agent.input_type = input_type
    agent.output_type = output_type
    agent.status = status

    db.commit()

    return RedirectResponse(
        "/agent-builder",
        status_code=303
    )
@app.get("/toggle-agent/{agent_id}")
def toggle_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):
    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    if not agent:
        return RedirectResponse(
            "/agent-builder",
            status_code=303
        )

    if agent.status == "Active":
        agent.status = "Disabled"
    else:
        agent.status = "Active"

    db.commit()

    return RedirectResponse(
            "/agent-builder",
            status_code=303
        )
@app.post("/execute-agent/{agent_id}")
def execute_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):

    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    result = f"{agent.agent_name} executed successfully"

    agent.output_history = result

    db.commit()

    return RedirectResponse(
        "/agent-builder",
        status_code=303
    )
@app.get("/workflow-builder")
def workflow_builder(
    request: Request,
    db: Session = Depends(get_db)
):

    workflows = db.query(
        Workflow
    ).all()

    agents = db.query(
        Agent
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="workflow_builder.html",
        context={
            "workflows": workflows,
            "agents": agents,
            **get_admin_context()
        }
    )
@app.post("/create-workflow")
def create_workflow(
    workflow_name: str = Form(...),
    step1_agent: int = Form(...),
    step2_agent: int = Form(None),
    step3_agent: int = Form(None),
    db: Session = Depends(get_db)
):

    workflow = Workflow(
        workflow_name=workflow_name
    )

    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    db.add(
        WorkflowStep(
            workflow_id=workflow.id,
            step_number=1,
            agent_id=step1_agent
        )
    )

    if step2_agent:
        db.add(
            WorkflowStep(
                workflow_id=workflow.id,
                step_number=2,
                agent_id=step2_agent
            )
        )

        if step3_agent:
            db.add(
                WorkflowStep(
                    workflow_id=workflow.id,
                    step_number=3,
                    agent_id=step3_agent
                )
            )

    db.commit()

    return RedirectResponse(
                url="/workflow-builder",
                status_code=303
            )
@app.get("/view-workflow/{workflow_id}")
def view_workflow(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id
    ).first()

    if not workflow:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found"
        )

    return templates.TemplateResponse(
        request=request,
        name="view_workflow.html",
        context={
            "workflow": workflow,
            **get_admin_context()
        }
    )
@app.get("/delete-workflow/{workflow_id}")
def delete_workflow(
    workflow_id: int,
    db: Session = Depends(get_db)
):
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id
    ).first()

    if workflow:
        db.delete(workflow)
        db.commit()

    return RedirectResponse(
            "/workflow-builder",
            status_code=303
        )
@app.get("/execute-workflow/{workflow_id}")
def execute_workflow_page(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id
    ).first()

    return templates.TemplateResponse(
        request=request,
        name="workflow_execution.html",
        context={
            "workflow": workflow,
            **get_admin_context()
        }
    )
@app.post("/run-workflow/{workflow_id}")
async def run_workflow(
    workflow_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id
    ).first()

    if not workflow:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found"
        )

    # Create Workflow Execution Record
    tracking_id = str(uuid.uuid4())

    workflow_execution = WorkflowExecution(
        tracking_id=tracking_id,
        workflow_id=workflow.id,
        workflow_name=workflow.workflow_name,
        input_data=file.filename,
        output_data="",
        status="Running",
        execution_type="Manual"
    )

    db.add(workflow_execution)
    db.commit()
    db.refresh(workflow_execution)
    print("================================")
    print("Workflow Execution Saved")
    print("ID:", workflow_execution.id)
    print("Tracking:", workflow_execution.tracking_id)
    print("================================")

    steps = db.query(WorkflowStep).filter(
        WorkflowStep.workflow_id == workflow_id
    ).order_by(
        WorkflowStep.step_number
    ).all()

    file_path = f"uploads/{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    extension = file.filename.split(".")[-1].lower()

    if extension == "pdf":
       current_output = extract_pdf_text(file_path)

    elif extension == "docx":
         current_output = extract_docx_text(file_path)

    elif extension == "txt":
         current_output = extract_txt_text(file_path)

    else:
        current_output = "Unsupported File Type"

    execution_log = []

    try:
        for step in steps:
            agent = db.query(Agent).filter(
                Agent.id == step.agent_id
            ).first()

            if not agent:
                continue

            execution_log.append(
                f"Step {step.step_number}: {agent.agent_name}"
            )

            # Text / Parser Agent
            if agent.output_type == "Text":
                execution_log.append(
                    "Document Parsed Successfully"
                )

            # Summary Agent
            elif agent.output_type == "Summary":
                current_output = generate_summary(current_output)
                execution_log.append("Summary Generated")

            # JSON Agent
            elif agent.output_type == "JSON":
                current_output = extract_json(current_output)
                execution_log.append("JSON Generated")

        # Success Update
        workflow_execution.output_data = str(current_output)
        workflow_execution.status = "Completed"
        workflow_execution.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        workflow_execution.status = "Failed"
        workflow_execution.output_data = str(e)
        workflow_execution.completed_at = datetime.utcnow()
        db.commit()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    return templates.TemplateResponse(
        request=request,
        name="workflow_execution.html",
        context={
            "workflow": workflow,
            "execution_log": execution_log,
            "result": current_output,
            "tracking_id": tracking_id,
            **get_admin_context()
        }
    )


@app.get("/llm-providers")
def llm_providers_page(
    request: Request,
    db: Session = Depends(get_db)
):

    if request.session.get("role_name") != "Admin":
        return RedirectResponse(
            "/",
            status_code=303
        )

    providers = db.query(
        LLMProvider
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="llm_providers.html",
        context={
            "providers": providers,
            **get_admin_context()
        }
    )
@app.post("/create-provider")
def create_provider(
    provider_name: str = Form(...),
    api_base_url: str = Form(...),
    db: Session = Depends(get_db)
):

    existing = db.query(
        LLMProvider
    ).filter(
        LLMProvider.provider_name == provider_name
    ).first()

    if existing:
        return RedirectResponse(
            "/llm-providers",
            status_code=303
        )

    provider = LLMProvider(
        provider_name=provider_name,
        api_base_url=api_base_url,
        status="Active"
    )

    db.add(provider)

    db.commit()

    return RedirectResponse(
        "/llm-providers",
        status_code=303
    )
@app.get("/toggle-provider/{provider_id}")
def toggle_provider(
    provider_id: int,
    db: Session = Depends(get_db)
):

    provider = db.query(
        LLMProvider
    ).filter(
        LLMProvider.id == provider_id
    ).first()

    if provider:

        if provider.status == "Active":
            provider.status = "Inactive"
        else:
            provider.status = "Active"

            db.commit()

            return RedirectResponse(
                "/llm-providers",
                status_code=303
            )
@app.get("/delete-provider/{provider_id}")
def delete_provider(
    provider_id: int,
    db: Session = Depends(get_db)
):

    provider = db.query(
        LLMProvider
    ).filter(
        LLMProvider.id == provider_id
    ).first()

    if provider:

        db.delete(provider)

        db.commit()

        return RedirectResponse(
            "/llm-providers",
            status_code=303
        )
@app.get("/seed-providers")
def seed_providers(
    db: Session = Depends(get_db)
):

    providers = [

        ("OpenAI", "https://api.openai.com/v1"),

        (
            "Azure OpenAI",
            "https://YOUR_RESOURCE.openai.azure.com"
        ),

        (
            "Google Gemini",
            "https://generativelanguage.googleapis.com"
        ),

        (
            "AWS Bedrock",
            "https://bedrock-runtime.amazonaws.com"
        ),

        (
            "Anthropic Claude",
            "https://api.anthropic.com"
        )

    ]

    for name, url in providers:

        existing = db.query(
            LLMProvider
        ).filter(
            LLMProvider.provider_name == name
        ).first()

        if not existing:

            db.add(
                LLMProvider(
                    provider_name=name,
                    api_base_url=url,
                    status="Active"
                )
            )

    db.commit()

    return {
                "message": "Providers added successfully"
            }
            
    
@app.get("/api-keys")
def api_keys_page(
    request: Request,
    db: Session = Depends(get_db)
):

    if request.session.get("role_name") != "Admin":
        return RedirectResponse(
            "/",
            status_code=303
        )

    api_keys = db.query(
        APIKey
    ).all()

    providers = db.query(
        LLMProvider
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="api_keys.html",
        context={
            "api_keys": api_keys,
            "providers": providers,
            **get_admin_context()
        }
    )
@app.post("/create-api-key")
def create_api_key(
    key_name: str = Form(...),
    provider_id: int = Form(...),
    api_key: str = Form(...),
    db: Session = Depends(get_db)
):

    key = APIKey(
        key_name=key_name,
        provider_id=provider_id,
        api_key=api_key,
        status="Active"
    )

    db.add(key)

    db.commit()

    return RedirectResponse(
        "/api-keys",
        status_code=303
    )
@app.get("/toggle-api-key/{key_id}")
def toggle_api_key(
    key_id: int,
    db: Session = Depends(get_db)
):

    key = db.query(
        APIKey
    ).filter(
        APIKey.id == key_id
    ).first()

    if key:

        if key.status == "Active":
            key.status = "Inactive"
        else:
            key.status = "Active"

        db.commit()

        return RedirectResponse(
                "/api-keys",
                status_code=303
            )
@app.get("/delete-api-key/{key_id}")
def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db)
):

    key = db.query(
        APIKey
    ).filter(
        APIKey.id == key_id
    ).first()

    if key:

        db.delete(key)

    db.commit()

    return RedirectResponse(
            "/api-keys",
            status_code=303
        )
@app.get("/test-providers")
def test_providers(
    db: Session = Depends(get_db)
):
    providers = db.query(LLMProvider).all()

    return [
        {
            "id": p.id,
            "provider_name": p.provider_name,
            "status": p.status
        }
        for p in providers
    ]


@app.post("/api/agents/{agent_name}")
def execute_agent_api(
    agent_name: str,
    payload: dict,
    x_api_key: str = Header(None),
    db: Session = Depends(get_db)
):

    print("Received API Key:", x_api_key)

    token = db.query(
        AgentAPIToken
    ).filter(
        AgentAPIToken.token == x_api_key
    ).first()

    print("Token Found:", token)

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )

    agent = db.query(Agent).filter(
        Agent.api_endpoint ==
        f"/api/agents/{agent_name}"
    ).first()

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found"
        )

    question = payload.get(
        "question",
        ""
    )

    answer = "Agent executed successfully"
    print("===== CREATING USAGE RECORD =====")

    usage = APIUsage(
        agent_id=agent.id,
        api_key=x_api_key,
        question=question,
        response=answer,
        status="Success"
    )

    print("Before db.add()")
    db.add(usage)

    print("Before commit()")
    db.commit()

    print("After commit()")
    print("Inserted Usage ID:", usage.id)

    return {"response": answer}


@app.get("/api-services")
def api_services(
    request: Request,
    db: Session = Depends(get_db)
):

    agents = db.query(Agent).all()

    return templates.TemplateResponse(
        request=request,
        name="api_services.html",
        context={
            "agents": agents,
            **get_admin_context()
        }
    )
@app.get("/generate-api-token/{agent_id}")
def generate_api_token(
    agent_id: int,
    db: Session = Depends(get_db)
):
    existing = db.query(AgentAPIToken).filter(
        AgentAPIToken.agent_id == agent_id
    ).first()

    token = str(uuid.uuid4())

    if existing:
        existing.token = token
    else:
        api_token = AgentAPIToken(
            token_name="Default Token",
            token=token,
            agent_id=agent_id,
            status="Active"
        )
        db.add(api_token)

    db.commit()

    return RedirectResponse(
      url=f"/view-key/{agent_id}",
        status_code=303
        )
@app.get("/test-published-agents")
def test_published_agents(
    db: Session = Depends(get_db)
):
    return db.query(Agent).all()
@app.get("/test-api-keys")
def test_api_keys(
    db: Session = Depends(get_db)
):
    return db.query(APIKey).all()
@app.get("/view-api/{agent_id}")
def view_api(
    agent_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found"
        )

    return templates.TemplateResponse(
        request=request,
        name="view_api.html",
        context={
            "agent": agent,
            **get_admin_context()
        }
    )
@app.get("/view-key/{agent_id}")
def view_key(
    agent_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    token = db.query(AgentAPIToken).filter(
        AgentAPIToken.agent_id == agent_id
    ).order_by(
        AgentAPIToken.id.desc()
    ).first()

    return templates.TemplateResponse(
        request=request,
        name="view_key.html",
        context={
            "token": token,
            **get_admin_context()
        }
    )
    
@app.get("/llm-models")
def llm_models_page(
    request: Request,
    db: Session = Depends(get_db)
):

    models = db.query(
        LLMModel
    ).all()

    providers = db.query(
        LLMProvider
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="llm_models.html",
        context={
            "models": models,
            "providers": providers,
            **get_admin_context()
        }
    )
    
@app.post("/create-model")
def create_model(
    provider_id: int = Form(...),
    model_name: str = Form(...),
    db: Session = Depends(get_db)
):

    model = LLMModel(
        provider_id=provider_id,
        model_name=model_name,
        status="Active"
    )

    db.add(model)
    db.commit()

    return RedirectResponse(
        "/llm-models",
        status_code=303
    )

@app.get("/seed-models")
def seed_models(
    db: Session = Depends(get_db)
):

    provider_models = {
        "OpenAI": [
            "GPT-4o",
            "GPT-4.1",
            "o4-mini"
        ],

        "Google Gemini": [
            "Gemini 2.5 Pro",
            "Gemini 2.5 Flash"
        ],

        "Anthropic Claude": [
            "Claude Sonnet 4",
            "Claude Opus 4"
        ],

        "AWS Bedrock": [
            "Claude",
            "Titan",
            "Nova"
        ]
    }

    for provider_name, models in provider_models.items():

        provider = db.query(
            LLMProvider
        ).filter(
            LLMProvider.provider_name ==
            provider_name
        ).first()

        if provider:

            for model_name in models:

                existing = db.query(
                    LLMModel
                ).filter(
                    LLMModel.model_name ==
                    model_name
                ).first()

                if not existing:

                    db.add(
                        LLMModel(
                            provider_id=provider.id,
                            model_name=model_name
                        )
                    )

    db.commit()

    return {
        "message": "Models Added"
        }
    
from fastapi.responses import JSONResponse

@app.get("/provider-models/{provider_id}")
def provider_models(
    provider_id: int,
    db: Session = Depends(get_db)
):
    models = db.query(
        LLMModel
    ).filter(
        LLMModel.provider_id == provider_id
    ).all()

    return [
        {
            "id": model.id,
            "model_name": model.model_name
        }
        for model in models
    ]
@app.get("/provider-api-keys/{provider_id}")
def provider_api_keys(
    provider_id: int,
    db: Session = Depends(get_db)
):

    api_keys = db.query(
        APIKey
    ).filter(
        APIKey.provider_id == provider_id
    ).all()

    return [
        {
            "id": key.id,
            "key_name": key.key_name
        }
        for key in api_keys
    ]
@app.get("/api-analytics")
def api_analytics(
    request: Request,
    db: Session = Depends(get_db)
):

    usage_records = db.query(
        APIUsage
    ).order_by(
        APIUsage.id.desc()
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="api_analytics.html",
        context={
            "usage_records": usage_records,
            **get_admin_context()
        }
    )
@app.get("/test-agents")
def test_agents(
    db: Session = Depends(get_db)
):
    return [
        {
            "id": a.id,
            "name": a.agent_name,
            "endpoint": a.api_endpoint
        }
        for a in db.query(Agent).all()
    ]
@app.get("/test-tokens")
def test_tokens(
    db: Session = Depends(get_db)
):
    return db.query(AgentAPIToken).all()

    
# ==========================================
# Resume Matcher
# ==========================================

def calculate_match(
    resume_text,
    job_description
):

    resume_words = set(
        resume_text.lower().split()
    )

    jd_words = set(
        job_description.lower().split()
    )

    matched_skills = list(
        resume_words.intersection(jd_words)
    )

    missing_skills = list(
        jd_words - resume_words
    )

    match_percentage = round(
        (
            len(matched_skills)
            / max(len(jd_words), 1)
        ) * 100,
        2
    )

    summary = (
        f"Candidate matches "
        f"{match_percentage}% "
        f"of the job requirements."
    )

    return {
        "match_percentage": match_percentage,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "summary": summary
    }


@app.get("/resume-matcher")
def resume_matcher_page(
    request: Request
):

    return templates.TemplateResponse(
        request=request,
        name="resume_matcher.html",
        context={
            **get_admin_context()
        }
    )


@app.post("/run-resume-matcher")
def run_resume_matcher(
    request: Request,
    resume_text: str = Form(...),
    job_description: str = Form(...)
):

    result = calculate_match(
        resume_text,
        job_description
    )

    return templates.TemplateResponse(
        request=request,
        name="resume_matcher.html",
        context={
            "resume_text": resume_text,
            "job_description": job_description,
            "result": json.dumps(
                result,
                indent=4
            ),
            **get_admin_context()
        }
    )
@app.get("/create-document-classifier-table")
def create_document_classifier_table():

    Base.metadata.create_all(bind=engine)

    return {
        "message": "Document Classifier table created"
    }
    
@app.get("/test-document-classifier")
def test_document_classifier(
    db: Session = Depends(get_db)
):
    return db.query(
        DocumentClassifier
    ).all()

@app.get("/document-classifier")
def document_classifier_page(
    request: Request
):
    return templates.TemplateResponse(
        request=request,
        name="document_classifier.html",
        context={
            **get_admin_context()
        }
    )
def classify_document(text):

    text = text.lower()

    if "skills" in text or "experience" in text:
        return "Resume"

    if "invoice" in text or "amount due" in text:
        return "Invoice"

    if "contract" in text or "agreement" in text:
        return "Contract"

    if "policy" in text:
        return "Policy Document"

    if "patient" in text or "diagnosis" in text:
        return "Medical Report"

    if "court" in text or "legal" in text:
        return "Legal Document"

    return "Other"


@app.post("/run-document-classifier")
async def run_document_classifier(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    file_path = f"uploads/{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    extension = file.filename.split(".")[-1].lower()

    if extension == "pdf":
       text = extract_pdf_text(file_path)

    elif extension == "docx":
        text = extract_docx_text(file_path)

    elif extension == "txt":
        text = extract_txt_text(file_path)

    else:
         text = ""

     # Classification
    document_type = classify_document(text)

            # Database Record
    record = DocumentClassifier(
      file_name=file.filename,
      document_type=document_type,
      confidence="100%"
            )

    db.add(record)
    db.commit()

    print("Detected Type:", document_type)

    return templates.TemplateResponse(
                request=request,
                name="document_classifier.html",
                context={
                    "document_name": file.filename,
                    "document_type": document_type,
                    "confidence": "100%",
                    **get_admin_context()
                }
            )
@app.get("/document-classifications")
def document_classifications(
    db: Session = Depends(get_db)
):
    return db.query(
        DocumentClassifier
    ).all()
    
@app.get("/document-classification-history")
def document_classification_history(
    request: Request,
    db: Session = Depends(get_db)
):

    records = db.query(
        DocumentClassifier
    ).order_by(
        DocumentClassifier.id.desc()
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="document_classification_history.html",
        context={
            "records": records,
            **get_admin_context()
        }
    )
@app.get("/resume-screening-agent")
def resume_screening_page(
    request: Request
):
    return templates.TemplateResponse(
        request=request,
        name="resume_screening.html",
        context={
            **get_admin_context()
        }
    )
@app.post("/run-resume-screening")
async def run_resume_screening(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    db: Session = Depends(get_db)
):
    # Save Resume
    file_path = f"uploads/{resume.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(resume.file, buffer)

        # Extract Resume Text
    extension = resume.filename.split(".")[-1].lower()

    if extension == "pdf":
         resume_text = extract_pdf_text(file_path)

    elif extension == "docx":
        resume_text = extract_docx_text(file_path)

    elif extension == "txt":
         resume_text = extract_txt_text(file_path)

    else:
         return {
             "error": "Only PDF, DOCX and TXT files are supported."
            }

  # Convert Resume Text to Upper Case
    resume_text = resume_text.upper()

        # Skills from JD
    jd_skills = [
       skill.strip().upper()
        for skill in job_description.split(",")
         if skill.strip()
        ]

        # Find Matched Skills
    matched_skills = []

    for skill in jd_skills:
        if skill in resume_text:
            matched_skills.append(skill)

                # Find Missing Skills
    missing_skills = []

    for skill in jd_skills:
        if skill not in matched_skills:
             missing_skills.append(skill)

     # Calculate Score
    total_skills = len(jd_skills)

    if total_skills > 0:
         score = round(
         (len(matched_skills) / total_skills) * 100,
                     2
             )
    else:
        score = 0

     # Candidate Status
    if score >= 80:
     status = "Strong Match"

    elif score >= 50:
        status = "Moderate Match"

    else:
        status = "Weak Match"

    # Return JSON Response
    return {
       "resume_file": resume.filename,
        "resume_score": score,
        "status": status,
        "matched_skills": matched_skills,
         "missing_skills": missing_skills
        }
        
    
def parse_resume(text):

    words = text.split()

    skills = []

    skill_keywords = [
        "python",
        "fastapi",
        "azure",
        "git",
        "docker",
        "kubernetes",
        "sql",
        "java",
        "react"
    ]

    for word in words:

        if word.lower() in skill_keywords:
            skills.append(word)

    return {
      "skills": skills
            }
    
    
@app.post("/api/resume-screening")
def resume_screening_api(
    payload: dict,
    x_api_key: str = Header(None),
    db: Session = Depends(get_db)
):

    token = db.query(
        AgentAPIToken
    ).filter(
        AgentAPIToken.token == x_api_key
    ).first()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )

    resume_text = payload.get(
        "resume_text",
        ""
    )

    job_description = payload.get(
        "job_description",
        ""
    )

    summary = generate_summary(
        resume_text
    )

    parsed_data = parse_resume(
        resume_text
    )

    resume_skills = " ".join(
        parsed_data["skills"]
    )

    result = calculate_match(
        resume_skills,
        job_description
    )

    usage = APIUsage(
        api_key=x_api_key,
        question="Resume Screening API",
        response=str(result),
        status="Success"
    )

    db.add(usage)
    db.commit()

    return {
        "summary": summary,
        "parsed_data": parsed_data,
        "match_result": result
    }
    
@app.get("/publish-resume-agent")
def publish_resume_agent(
    db: Session = Depends(get_db)
):

    agent = db.query(Agent).filter(
        Agent.agent_name == "Resume Matcher Agent"
    ).first()

    if agent:

        agent.is_published = True

        agent.api_endpoint = (
            "/api/agents/resume-matcher-agent"
        )

        db.commit()

        return {
            "message": "Published"
        }
        
@app.post("/api/execute-workflow/{workflow_id}")
def execute_workflow_api(
    workflow_id: int,
    payload: dict,
    x_api_key: str = Header(None),
    db: Session = Depends(get_db)
):

    token = db.query(
        AgentAPIToken
    ).filter(
        AgentAPIToken.token == x_api_key,
        AgentAPIToken.status == "Active"
    ).first()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )

    workflow = db.query(
        Workflow
    ).filter(
        Workflow.id == workflow_id
    ).first()

    if not workflow:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found"
        )

    steps = db.query(
        WorkflowStep
    ).filter(
        WorkflowStep.workflow_id == workflow_id
    ).order_by(
        WorkflowStep.step_number
    ).all()

    resume_text = payload.get(
        "resume_text",
        ""
    )

    job_description = payload.get(
        "job_description",
        ""
    )

    current_output = resume_text

    execution_log = []

    for step in steps:

        agent = db.query(
            Agent
        ).filter(
            Agent.id == step.agent_id
        ).first()

        if not agent:
            continue

        execution_log.append(
            f"Step {step.step_number}: {agent.agent_name}"
        )

        if agent.agent_name == "Parser Agent":
            current_output = parse_resume(
                current_output
            )

        elif agent.agent_name == "Summary Agent":
            current_output = generate_summary(
                str(current_output)
            )

        elif agent.agent_name == "JSON Agent":
            current_output = extract_json(
                str(current_output)
            )

        elif agent.agent_name == "Resume Matcher Agent":
            current_output = calculate_match(
                str(current_output),
                job_description
            )

            db.add(
                APIUsage(
                    api_key=x_api_key,
                    question="Workflow Execution",
                    response=str(current_output),
                    status="Success"
                )
            )

    db.commit()

    return {
      "workflow": workflow.workflow_name,
       "execution_log": execution_log,
        "result": current_output
            }
    
@app.get("/agent-marketplace")
def agent_marketplace(
    request: Request,
    db: Session = Depends(get_db)
):

    agents = db.query(
        Agent
    ).filter(
        Agent.is_published == True
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="agent_marketplace.html",
        context={
            "agents": agents,
            **get_admin_context()
        }
    )
@app.get("/add-input-type-column")
def add_input_type_column(db: Session = Depends(get_db)):
    db.execute(text("""
    ALTER TABLE agents
    ADD COLUMN input_type TEXT
    """))
    db.commit()

    return {"message": "input_type column added"}


@app.get("/test-agents-full")
def test_agents_full(
    db: Session = Depends(get_db)
):
    return [
        {
            "id": a.id,
            "agent_name": a.agent_name,
            "input_type": a.input_type,
            "output_type": a.output_type
        }
        for a in db.query(Agent).all()
    ]
@app.get("/check-input-type")
def check_input_type(
    db: Session = Depends(get_db)
):
    result = db.execute(
        text("PRAGMA table_info(agents)")
    ).fetchall()

    return [
        dict(row._mapping)
        for row in result
    ]
    
@app.get("/upgrade-agent-studio")
def upgrade_agent_studio(
    db: Session = Depends(get_db)
):
    try:
        db.execute(
            text(
                """
                ALTER TABLE agents
                ADD COLUMN agent_category TEXT
                """
            )
        )
    except:
        pass

    try:
        db.execute(
            text(
                """
                ALTER TABLE agents
                ADD COLUMN processing_mode TEXT
                """
            )
        )
    except:
        pass

    db.commit()

    return {
        "message": "Agent Studio upgraded"
    }
    
@app.get("/test-agent/{agent_id}")
def test_agent_page(
    agent_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    return templates.TemplateResponse(
        request=request,
        name="test_agent.html",
        context={
            "agent": agent,
            **get_admin_context()
        }
    )
@app.post("/run-test-agent/{agent_id}")
async def run_test_agent(
    agent_id: int,
    request: Request,
    input_text: str = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):

    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found"
        )

    data = ""

    if input_text:
     data = input_text

    if file:

        file_path = f"uploads/{file.filename}"

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(
                file.file,
                buffer
            )

            extension = file.filename.split(".")[-1].lower()

            if extension == "pdf":
                data = extract_pdf_text(file_path)

            elif extension == "docx":
                data = extract_docx_text(file_path)

            elif extension == "txt":
                data = extract_txt_text(file_path)

    output = execute_dynamic_agent(
    agent,
    data
)
          
    execution = AgentExecution(
          tracking_id=str(uuid.uuid4()),
          agent_id=agent.id,
          input_data=data,
          output_data=str(output),
          status="Completed",
          execution_type="Test"
        )

    db.add(execution)

    db.commit()

    return templates.TemplateResponse(
                            request=request,
                            name="test_agent.html",
                            context={
                                "agent": agent,
                                "output": output,
                                **get_admin_context()
                            }
                        )
    
@app.get("/agent-executions")
def agent_executions(
    request: Request,
    db: Session = Depends(get_db)
):

    executions = db.query(
        AgentExecution
    ).order_by(
        AgentExecution.id.desc()
    ).all()

    total_executions = db.query(
        AgentExecution
    ).count()

    pending_count = db.query(
        AgentExecution
    ).filter(
        AgentExecution.status == "Pending"
    ).count()

    completed_count = db.query(
        AgentExecution
    ).filter(
        AgentExecution.status == "Completed"
    ).count()

    failed_count = db.query(
        AgentExecution
    ).filter(
        AgentExecution.status == "Failed"
    ).count()

    return templates.TemplateResponse(
        request=request,
        name="agent_executions.html",
        context={
            "executions": executions,
            "total_executions": total_executions,
            "pending_count": pending_count,
            "completed_count": completed_count,
            "failed_count": failed_count,
            **get_admin_context()
        }
    )
    
@app.get("/execution-details/{execution_id}")
def execution_details(
    execution_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    execution = db.query(
        AgentExecution
    ).filter(
        AgentExecution.id == execution_id
    ).first()

    return templates.TemplateResponse(
        request=request,
        name="execution_details.html",
        context={
            "execution": execution,
            **get_admin_context()
        }
    )
    
    
@app.post("/run-agent-async/{agent_id}")
async def run_agent_async(
    agent_id: int,
    background_tasks: BackgroundTasks,
    input_text: str = Form(""),
    db: Session = Depends(get_db)
):

    agent = db.query(Agent).filter(
        Agent.id == agent_id
    ).first()

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found"
        )

    tracking_id = str(uuid.uuid4())

    execution = AgentExecution(
        tracking_id=tracking_id,
        agent_id=agent.id,
        input_data=input_text,
        output_data="",
        status="Pending",
        execution_type="Async"
    )

    db.add(execution)

    db.commit()

    db.refresh(execution)

    background_tasks.add_task(
        process_agent_execution,
        execution.id
    )

    return {
        "tracking_id": tracking_id,
        "status": "Pending"
    }
    
@app.get("/agent-status/{tracking_id}")
def agent_status(
    tracking_id: str,
    db: Session = Depends(get_db)
):

    execution = db.query(
        AgentExecution
    ).filter(
        AgentExecution.tracking_id ==
        tracking_id
    ).first()

    if not execution:
        raise HTTPException(
            status_code=404,
            detail="Tracking ID not found"
        )

    return {
        "tracking_id":
            execution.tracking_id,

            "status":
                execution.status
            }
    
@app.get("/agent-result/{tracking_id}")
def agent_result(
    tracking_id: str,
    db: Session = Depends(get_db)
):

    execution = db.query(
        AgentExecution
    ).filter(
        AgentExecution.tracking_id ==
        tracking_id
    ).first()

    if not execution:
        raise HTTPException(
            status_code=404,
            detail="Tracking ID not found"
        )

    return {
        "tracking_id":
            execution.tracking_id,

            "status":
                execution.status,

                "output":
                    execution.output_data
                }
    
@app.get("/complete-execution/{tracking_id}")
def complete_execution(
    tracking_id: str,
    db: Session = Depends(get_db)
):

    execution = db.query(
        AgentExecution
    ).filter(
        AgentExecution.tracking_id ==
        tracking_id
    ).first()

    if not execution:
        raise HTTPException(
            status_code=404,
            detail="Execution not found"
        )

    execution.output_data = (
        "Agent Execution Completed"
    )

    execution.status = "Completed"

    execution.completed_at = (
        datetime.utcnow()
    )

    db.commit()

    return {
        "message": "Execution completed"
    }
def execute_dynamic_agent(
    agent,
    data
):

    output_type = (
        agent.output_type or ""
    ).lower()

    if output_type == "summary":

        return generate_summary(data)

    elif output_type == "json":

        return extract_json(data)

    elif output_type == "text":

        return data

    return data

@app.get("/publish-workflow/{workflow_id}")
def publish_workflow(
    workflow_id: int,
    db: Session = Depends(get_db)
):

    workflow = db.query(
        Workflow
    ).filter(
        Workflow.id == workflow_id
    ).first()

    if workflow:

        workflow.is_published = True

        workflow.api_endpoint = (
            f"/api/workflows/"
            f"{workflow.workflow_name.lower().replace(' ','-')}"
        )

    db.commit()

    return RedirectResponse(
            "/workflow-builder",
            status_code=303
        )
@app.get("/workflow-executions", response_class=HTMLResponse)
def workflow_executions(
    request: Request,
    db: Session = Depends(get_db)
):
    executions = db.query(
        WorkflowExecution
    ).order_by(
        WorkflowExecution.id.desc()
    ).all()

    total_count = len(executions)

    completed_count = len([
        e for e in executions
        if e.status == "Completed"
    ])

    running_count = len([
        e for e in executions
        if e.status == "Running"
    ])

    failed_count = len([
        e for e in executions
        if e.status == "Failed"
    ])

    return templates.TemplateResponse(
        request,
        "workflow_executions.html",
        {
            "executions": executions,
            "total_count": total_count,
            "completed_count": completed_count,
            "running_count": running_count,
            "failed_count": failed_count
        }
    )
    
@app.get("/workflow-execution/{execution_id}", response_class=HTMLResponse)
def workflow_execution_detail(
    execution_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    execution = (
        db.query(WorkflowExecution)
        .filter(WorkflowExecution.id == execution_id)
        .first()
    )

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    return templates.TemplateResponse(
    request,
    "workflow_execution_detail.html",
    {
        "execution": execution
    }
)
@app.get("/upgrade-workflow-executions")
def upgrade_workflow_executions(
    db: Session = Depends(get_db)
):

    try:
        db.execute(text("""
        ALTER TABLE workflow_executions
        ADD COLUMN execution_type TEXT
        """))
    except:
        pass

    try:
        db.execute(text("""
        ALTER TABLE workflows
        ADD COLUMN is_published BOOLEAN
        """))
    except:
        pass

    try:
        db.execute(text("""
        ALTER TABLE workflows
        ADD COLUMN api_endpoint TEXT
        """))
    except:
        pass

    db.commit()

    return {
        "message": "Workflow tables upgraded"
    }
@app.get("/test-workflow-executions")
def test_workflow_executions(db: Session = Depends(get_db)):
    executions = db.query(WorkflowExecution).all()

    return [
        {
            "id": e.id,
            "tracking_id": e.tracking_id,
            "workflow_name": e.workflow_name,
            "status": e.status
        }
        for e in executions
    ]