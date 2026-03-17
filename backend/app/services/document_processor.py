"""文档处理编排服务 - 串联 Step 1 全流程"""
from loguru import logger

from app.services.data_manager import data_manager
from app.services.ocr_correction import ocr_correction_service
from app.services.structure_parser import structure_parser
from app.services.chunker import chunker_service
from app.services.role_annotator import role_annotator_service


class DocumentProcessor:
    """编排 Step 1 全流程：OCR 纠错 → 结构解析 → 分块 → 角色标注"""

    async def process_document(self, doc_id: str) -> None:
        """
        处理一个文档，依次执行 Step 1 的所有步骤。

        Args:
            doc_id: 文档 ID
        """
        doc = data_manager.get_document(doc_id)
        if not doc:
            raise ValueError(f"Document {doc_id} not found")

        try:
            # ─── Step 1.1: OCR 纠错 ───
            logger.info(f"[{doc_id}] Step 1.1: OCR correction")
            doc.status = "correcting"
            data_manager.update_document(doc)

            original_text = data_manager.get_original_text(doc_id)
            if not original_text:
                raise ValueError(f"No original text for document {doc_id}")

            corrected_text, corrections, ocr_reviews = (
                await ocr_correction_service.correct_text(original_text)
            )
            data_manager.save_corrected_text(doc_id, corrected_text)
            data_manager.save_corrections(doc_id, corrections)

            # ─── Step 1.2: 结构解析 ───
            logger.info(f"[{doc_id}] Step 1.2: Structure parsing")
            doc.status = "parsing"
            data_manager.update_document(doc)

            patterns = data_manager.load_level_patterns()
            tree = structure_parser.parse(corrected_text, patterns)
            data_manager.save_tree(doc_id, tree.to_dict())

            # ─── Step 1.3: 分块 ───
            logger.info(f"[{doc_id}] Step 1.3: Chunking")
            doc.status = "chunking"
            data_manager.update_document(doc)

            chunks = chunker_service.chunk_tree(
                root=tree,
                document_id=doc_id,
                source_file=doc.filename,
            )

            # ─── Step 1.4: 角色标注 ───
            logger.info(f"[{doc_id}] Step 1.4: Role annotation")
            role_registry = data_manager.load_role_registry()
            chunks, role_reviews = role_annotator_service.annotate_chunks(chunks, role_registry)

            # 保存所有产出
            data_manager.save_chunks(doc_id, chunks)
            data_manager.save_role_registry(role_registry)

            # 合并审核条目
            all_reviews = ocr_reviews + role_reviews
            data_manager.save_reviews(doc_id, all_reviews)

            # 更新文档状态
            doc.status = "completed"
            doc.chunk_count = len(chunks)
            data_manager.update_document(doc)

            logger.info(
                f"[{doc_id}] Processing complete: "
                f"{len(chunks)} chunks, {len(corrections)} corrections, {len(all_reviews)} reviews"
            )

        except Exception as e:
            logger.error(f"[{doc_id}] Processing failed: {e}")
            doc.status = "error"
            doc.error_message = str(e)
            data_manager.update_document(doc)
            raise

    async def reprocess_from_parsing(self, doc_id: str) -> None:
        """从结构解析步骤开始重新处理（用于人工修正纠错结果后）"""
        doc = data_manager.get_document(doc_id)
        if not doc:
            raise ValueError(f"Document {doc_id} not found")

        try:
            corrected_text = data_manager.get_corrected_text(doc_id)
            if not corrected_text:
                raise ValueError(f"No corrected text for {doc_id}")

            # Step 1.2
            logger.info(f"[{doc_id}] Re-processing from Step 1.2")
            doc.status = "parsing"
            data_manager.update_document(doc)

            patterns = data_manager.load_level_patterns()
            tree = structure_parser.parse(corrected_text, patterns)
            data_manager.save_tree(doc_id, tree.to_dict())

            # Step 1.3
            doc.status = "chunking"
            data_manager.update_document(doc)

            chunks = chunker_service.chunk_tree(
                root=tree,
                document_id=doc_id,
                source_file=doc.filename,
            )

            # Step 1.4
            role_registry = data_manager.load_role_registry()
            chunks, role_reviews = role_annotator_service.annotate_chunks(chunks, role_registry)

            data_manager.save_chunks(doc_id, chunks)
            data_manager.save_role_registry(role_registry)
            data_manager.save_reviews(doc_id, role_reviews)

            doc.status = "completed"
            doc.chunk_count = len(chunks)
            data_manager.update_document(doc)

            logger.info(f"[{doc_id}] Re-processing complete: {len(chunks)} chunks")

        except Exception as e:
            logger.error(f"[{doc_id}] Re-processing failed: {e}")
            doc.status = "error"
            doc.error_message = str(e)
            data_manager.update_document(doc)
            raise


document_processor = DocumentProcessor()
