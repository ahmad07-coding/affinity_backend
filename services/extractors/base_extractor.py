"""
Base classes and interfaces for PDF extraction
Defines abstract base class for different PDF extraction engines
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any


@dataclass
class Word:
    """Represents a word in a PDF with its bounding box"""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page_number: int

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        """Return bounding box as tuple (x0, y0, x1, y1)"""
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class TableCell:
    """Represents a cell in an extracted table"""
    text: str
    row: int
    col: int
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass
class Table:
    """Represents an extracted table with cells"""
    cells: List[List[Optional[str]]]  # 2D array of cell values
    page_number: int
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def num_rows(self) -> int:
        return len(self.cells)

    @property
    def num_cols(self) -> int:
        return max(len(row) for row in self.cells) if self.cells else 0


@dataclass
class ExtractionResult:
    """
    Result from PDF extraction containing text, tables, and metadata
    """
    text: str
    pages: List[Dict[str, Any]]
    tables: List[Table] = field(default_factory=list)
    words: List[Word] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    extractor_name: str = "unknown"

    @property
    def num_pages(self) -> int:
        return len(self.pages)

    @property
    def total_chars(self) -> int:
        return len(self.text)


class BasePDFExtractor(ABC):
    """
    Abstract base class for PDF extraction engines
    All extractors (pdfplumber, pdfminer.six, etc.) should implement this interface
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this extractor"""
        pass

    @abstractmethod
    def extract(self, filepath: str) -> ExtractionResult:
        """
        Extract all data from a PDF file

        Args:
            filepath: Path to the PDF file

        Returns:
            ExtractionResult containing text, tables, words, and metadata
        """
        pass

    @abstractmethod
    def extract_text(self, page) -> str:
        """
        Extract text from a single page

        Args:
            page: Page object (type depends on extractor implementation)

        Returns:
            Extracted text as string
        """
        pass

    @abstractmethod
    def extract_tables(self, page) -> List[Table]:
        """
        Extract tables from a single page

        Args:
            page: Page object (type depends on extractor implementation)

        Returns:
            List of Table objects
        """
        pass

    @abstractmethod
    def extract_words(self, page) -> List[Word]:
        """
        Extract words with bounding boxes from a single page

        Args:
            page: Page object (type depends on extractor implementation)

        Returns:
            List of Word objects with coordinates
        """
        pass

    @abstractmethod
    def get_page_dimensions(self, page) -> Tuple[float, float]:
        """
        Get the dimensions of a page

        Args:
            page: Page object (type depends on extractor implementation)

        Returns:
            Tuple of (width, height) in points
        """
        pass

    def validate_file(self, filepath: str) -> bool:
        """
        Validate that the file exists and can be processed

        Args:
            filepath: Path to the PDF file

        Returns:
            True if valid, raises exception otherwise
        """
        import os
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        if not filepath.lower().endswith('.pdf'):
            raise ValueError(f"File must be a PDF: {filepath}")

        return True
