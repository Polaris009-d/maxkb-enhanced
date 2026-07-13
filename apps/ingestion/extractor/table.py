# coding=utf-8
"""
PDF table extraction using camelot-py or pdfplumber.
Extracts structured table data from PDFs and stores as JSON in paragraph.meta.
"""
import json
import logging
from io import BytesIO

logger = logging.getLogger("maxkb.table_extract")


class TableExtractor:
    """Extract tables from PDF files and return structured JSON.

    Falls back gracefully: if table extraction libraries aren't installed,
    returns empty results rather than crashing.
    """

    @staticmethod
    def extract_tables_pdfplumber(pdf_bytes: bytes) -> list:
        """Extract tables using pdfplumber (lighter dependency).

        Returns list of {page, table_index, headers, rows, raw_text}
        """
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber not installed, skipping table extraction")
            return []

        tables = []
        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    extracted = page.extract_tables()
                    for tidx, table in enumerate(extracted):
                        if not table or len(table) < 2:
                            continue
                        headers = [str(c or "") for c in table[0]]
                        rows = [[str(c or "") for c in row] for row in table[1:]]
                        # Convert to list of dicts for JSON
                        row_dicts = []
                        for row in rows:
                            row_dict = {}
                            for i, header in enumerate(headers):
                                row_dict[header] = row[i] if i < len(row) else ""
                            row_dicts.append(row_dict)

                        tables.append(
                            {
                                "page": page_num + 1,
                                "table_index": tidx,
                                "headers": headers,
                                "row_count": len(rows),
                                "data": row_dicts,
                                "raw_text": "\n".join(" | ".join(r) for r in rows),
                            }
                        )
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {e}")

        return tables

    @staticmethod
    def extract_tables_camelot(pdf_path: str) -> list:
        """Extract tables using camelot-py (lattice mode, more accurate).

        Requires camelot-py and ghostscript installed.
        """
        try:
            import camelot
        except ImportError:
            logger.warning("camelot-py not installed")
            return []

        tables = []
        try:
            # Try lattice mode first (for bordered tables)
            extracted = camelot.read_pdf(pdf_path, pages="all", flavor="lattice")
            if len(extracted) == 0:
                # Fall back to stream mode (for borderless tables)
                extracted = camelot.read_pdf(pdf_path, pages="all", flavor="stream")

            for tidx, table in enumerate(extracted):
                df = table.df
                if df.empty or len(df) < 2:
                    continue
                headers = [str(c) for c in df.iloc[0].tolist()]
                rows = [
                    [str(c) for c in df.iloc[i].tolist()] for i in range(1, len(df))
                ]
                tables.append(
                    {
                        "page": table.page,
                        "table_index": tidx,
                        "headers": headers,
                        "row_count": len(rows),
                        "accuracy": table.parsing_report.get("accuracy", 0),
                        "raw_text": table.df.to_csv(index=False),
                    }
                )
        except Exception as e:
            logger.warning(f"camelot extraction failed: {e}")

        return tables

    @staticmethod
    def extract_tables(file_bytes: bytes, file_path: str = None) -> dict:
        """Main entry point: extract tables from PDF, return structured result.

        Returns:
            {"tables": [...], "table_count": N, "method": "pdfplumber"|"camelot"}
        """
        # Try pdfplumber first (no external deps beyond pip)
        tables = TableExtractor.extract_tables_pdfplumber(file_bytes)
        method = "pdfplumber"

        # Fall back to camelot if available and pdfplumber got nothing
        if not tables and file_path:
            tables = TableExtractor.extract_tables_camelot(file_path)
            method = "camelot"

        return {
            "tables": tables,
            "table_count": len(tables),
            "method": method,
        }
