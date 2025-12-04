from typing import Optional

from pydantic import BaseModel, Field


class Photo(BaseModel):
    file_id: str
    file_unique_id: str
    width: int
    height: int
    file_size: Optional[int]


class Thumbnail(BaseModel):
    file_id: str
    file_unique_id: str
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


class Video(BaseModel):
    duration: int
    width: int
    height: int
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    thumbnail: Optional[Thumbnail] = None
    thumb: Optional[Thumbnail] = None
    file_id: str
    file_unique_id: str
    file_size: Optional[int] = None


class User(BaseModel):
    id: int
    is_bot: bool
    first_name: str
    last_name: Optional[str]
    username: Optional[str]
    language_code: Optional[str]


class Chat(BaseModel):
    id: int
    type: str
    first_name: Optional[str]
    last_name: Optional[str]
    username: Optional[str]


class Document(BaseModel):
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    thumbnail: Optional[Thumbnail] = None
    thumb: Optional[Thumbnail] = None
    file_id: str
    file_unique_id: str
    file_size: Optional[int] = None


class Message(BaseModel):
    message_id: int
    date: int
    chat: Chat
    from_: User = Field(..., alias="from")
    text: Optional[str] = None
    caption: Optional[str] = None
    media_group_id: Optional[str] = None
    document: Optional[Document] = None
    photo: Optional[list[Photo]] = None
    video: Optional[Video] = None


class Update(BaseModel):
    update_id: int
    message: Optional[Message]
