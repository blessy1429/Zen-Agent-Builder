from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Text,
    Boolean,
    DateTime
)

from sqlalchemy.orm import relationship

from database import Base


# ==================================
# Role Table
# ==================================
class Role(Base):
    __tablename__ = "roles"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String,
        unique=True,
        nullable=False
    )

    status = Column(
        String,
        default="Active"
    )

    users = relationship(
        "User",
        back_populates="role"
    )


    # ==================================
    # Module Table
    # ==================================
class Module(Base):
    __tablename__ = "modules"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String,
        unique=True,
        nullable=False
    )

    status = Column(
        String,
        default="Active"
    )


    # ==================================
    # Role Module Mapping
    # ==================================
class RoleModule(Base):
    __tablename__ = "role_modules"

    id = Column(
        Integer,
        primary_key=True
    )

    role_id = Column(
        Integer,
        ForeignKey("roles.id")
    )

    module_id = Column(
        Integer,
        ForeignKey("modules.id")
    )

    role = relationship("Role")

    module = relationship("Module")


    # ==================================
    # Knowledge Base
    # ==================================
class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(
        Integer,
        primary_key=True
    )

    file_name = Column(String)

    source_type = Column(String)

    source_path = Column(String)

    status = Column(
        String,
        default="Loading"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    chunks = relationship(
        "DocumentChunk",
        back_populates="knowledge",
        cascade="all, delete-orphan"
    )


    # ==================================
    # User Table
    # ==================================
class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True
    )

    username = Column(
        String,
        unique=True,
        nullable=False
    )

    email = Column(
        String,
        unique=True,
        nullable=False
    )

    password = Column(
        String,
        nullable=False
    )

    role_id = Column(
        Integer,
        ForeignKey("roles.id")
    )

    status = Column(
        String,
        default="Active"
    )

    role = relationship(
        "Role",
        back_populates="users"
    )


    # ==================================
    # Document Chunks
    # ==================================
class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    knowledge_id = Column(
        Integer,
        ForeignKey("knowledge_base.id")
    )

    chunk_text = Column(Text)

    knowledge = relationship(
        "KnowledgeBase",
        back_populates="chunks"
    )


    # ==================================
    # Agent Builder
    # ==================================
class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)

    # Basic Information
    agent_name = Column(String)
    agent_category = Column(String)

    # Prompt Engineering
    prompt = Column(Text)

    # Dynamic Input / Output
    input_type = Column(String)
    output_type = Column(String)

    # Execution
    processing_mode = Column(
        String,
        default="Sync"
    )

    # Optional Knowledge Base
    knowledge_base_name = Column(String)

    # Status
    status = Column(String)

    # LLM Configuration
    provider_id = Column(
        Integer,
        ForeignKey("llm_providers.id"),
        nullable=True
    )

    model_name = Column(String)

    model_id = Column(
        Integer,
        ForeignKey("llm_models.id"),
        nullable=True
    )

    api_key_id = Column(
        Integer,
        ForeignKey("api_keys.id"),
        nullable=True
    )

    # Publishing
    is_published = Column(
        Boolean,
        default=False
    )

    api_endpoint = Column(String)

    provider = relationship(
        "LLMProvider"
    )

    model = relationship(
        "LLMModel"
    )

    api_key = relationship(
        "APIKey"
    )
    
class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id = Column(
        Integer,
        primary_key=True
    )

    workflow_id = Column(
        Integer,
        ForeignKey("workflows.id")
    )

    step_number = Column(Integer)

    agent_id = Column(
        Integer,
        ForeignKey("agents.id")
    )
class LLMProvider(Base):
    __tablename__ = "llm_providers"

    id = Column(Integer, primary_key=True)

    provider_name = Column(String)

    api_base_url = Column(String)

    status = Column(
        String,
        default="Active"
    )

    api_keys = relationship(
        "APIKey",
        back_populates="provider"
    )
class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)

    key_name = Column(String)

    provider_id = Column(
        Integer,
        ForeignKey("llm_providers.id")
    )

    api_key = Column(String)

    status = Column(
        String,
        default="Active"
    )

    provider = relationship(
    "LLMProvider",
    back_populates="api_keys"
)
    
class AgentAPIToken(Base):
    __tablename__ = "agent_api_tokens"

    id = Column(
        Integer,
        primary_key=True
    )

    token_name = Column(String)

    token = Column(String)

    agent_id = Column(
        Integer,
        ForeignKey("agents.id")
    )

    status = Column(
        String,
        default="Active"
    )

    agent = relationship("Agent")

class LLMModel(Base):
    __tablename__ = "llm_models"

    id = Column(Integer, primary_key=True, index=True)

    provider_id = Column(
        Integer,
        ForeignKey("llm_providers.id")
    )

    model_name = Column(String)

    status = Column(
        String,
        default="Active"
    )

    provider = relationship(
        "LLMProvider"
    )

from datetime import datetime

class APIUsage(Base):
    __tablename__ = "api_usage"

    id = Column(
        Integer,
        primary_key=True
    )

    agent_id = Column(
        Integer,
        ForeignKey("agents.id")
    )

    api_key = Column(String)

    question = Column(Text)

    response = Column(Text)

    request_time = Column(
        DateTime,
        default=datetime.utcnow
    )

    status = Column(String)

    agent = relationship(
        "Agent"
    )

class DocumentClassifier(Base):
    __tablename__ = "document_classifier"

    id = Column(Integer, primary_key=True, index=True)

    file_name = Column(String, nullable=False)

    document_type = Column(String, nullable=False)

    confidence = Column(String, default="100%")

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )
    

class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id = Column(Integer, primary_key=True)

    tracking_id = Column(String)

    agent_id = Column(
        Integer,
        ForeignKey("agents.id")
    )

    input_data = Column(Text)

    output_data = Column(Text)

    status = Column(String)

    execution_type = Column(String)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    completed_at = Column(
        DateTime,
        nullable=True
    )

    agent = relationship("Agent")
    
class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id = Column(Integer, primary_key=True, index=True)

    tracking_id = Column(String)

    workflow_id = Column(Integer)

    workflow_name = Column(String)

    input_data = Column(Text)

    output_data = Column(Text)

    status = Column(String)

    execution_type = Column(String)

    started_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    completed_at = Column(
        DateTime,
        nullable=True
    )
    
class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True)

    workflow_name = Column(String)

    is_published = Column(
        Boolean,
        default=False
    )

    api_endpoint = Column(String)