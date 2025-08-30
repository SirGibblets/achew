from ..models.chapter import ChapterData
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..services.processing_pipeline import ProcessingPipeline

from pydantic import BaseModel


class ChapterOperation(BaseModel):

    def apply(self, pipeline: "ProcessingPipeline"):
        pass

    def undo(self, pipeline: "ProcessingPipeline"):
        pass

    def find_chapter(self, pipeline: "ProcessingPipeline", chapter_id: str) -> ChapterData:
        for chapter in pipeline.chapters:
            if chapter.id == chapter_id:
                return chapter
        raise ValueError(f"Chapter with id {chapter_id} not found")


class BatchChapterOperation(ChapterOperation):
    operations: list[ChapterOperation]

    def apply(self, pipeline: "ProcessingPipeline"):
        for op in self.operations:
            op.apply(pipeline)

    def undo(self, pipeline: "ProcessingPipeline"):
        for op in reversed(self.operations):
            op.undo(pipeline)


class AddChapterOperation(ChapterOperation):
    chapter: ChapterData

    def apply(self, pipeline: "ProcessingPipeline"):
        insert_index = 0
        for i, existing_chapter in enumerate(pipeline.chapters):
            if existing_chapter.timestamp > self.chapter.timestamp:
                insert_index = i
                break
            insert_index = i + 1

        pipeline.chapters.insert(insert_index, self.chapter)
        pass

    def undo(self, pipeline: "ProcessingPipeline"):
        chapter = self.find_chapter(pipeline, self.chapter.id)
        pipeline.chapters.remove(chapter)
        pass


class DeleteChapterOperation(ChapterOperation):
    chapter_id: str

    def apply(self, pipeline: "ProcessingPipeline"):
        self.find_chapter(pipeline, self.chapter_id).deleted = True

    def undo(self, pipeline: "ProcessingPipeline"):
        self.find_chapter(pipeline, self.chapter_id).deleted = False


class RestoreChapterOperation(ChapterOperation):
    chapter_id: str
    old_title: str = ""
    new_title: Optional[str] = None

    def apply(self, pipeline: "ProcessingPipeline"):
        chapter = self.find_chapter(pipeline, self.chapter_id)
        chapter.selected = True
        chapter.deleted = False
        if self.new_title:
            self.old_title = chapter.current_title
            chapter.current_title = self.new_title

    def undo(self, pipeline: "ProcessingPipeline"):
        chapter = self.find_chapter(pipeline, self.chapter_id)
        if self.new_title:
            chapter.current_title = self.old_title
        chapter.deleted = True


class EditTitleOperation(ChapterOperation):
    chapter_id: str
    old_title: str = ""
    new_title: str

    def apply(self, pipeline: "ProcessingPipeline"):
        chapter = self.find_chapter(pipeline, self.chapter_id)
        self.old_title = chapter.current_title
        chapter.current_title = self.new_title

    def undo(self, pipeline: "ProcessingPipeline"):
        chapter = self.find_chapter(pipeline, self.chapter_id)
        chapter.current_title = self.old_title


class AICleanupOperation(ChapterOperation):
    chapter_id: str
    old_title: str
    new_title: str
    selected: bool = True

    def apply(self, pipeline: "ProcessingPipeline"):
        chapter = self.find_chapter(pipeline, self.chapter_id)
        chapter.current_title = self.new_title
        chapter.selected = self.selected

    def undo(self, pipeline: "ProcessingPipeline"):
        chapter = self.find_chapter(pipeline, self.chapter_id)
        chapter.current_title = self.old_title
        chapter.selected = True
