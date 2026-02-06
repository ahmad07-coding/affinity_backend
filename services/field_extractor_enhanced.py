"""
Enhanced Part VIII Extraction Methods
Fixes for Row 7a and other missing fields
"""
import re
from typing import List, Optional


def extract_row_7a_enhanced(section: str, field_extractor) -> tuple:
    """
    Enhanced extraction for Row 7a (Gross sales - Securities vs Other)
    Handles multiple text variations and formats

    Returns: (gross_sales_securities, gross_sales_other)
    """
    # Pattern variations for different PDFs
    patterns = [
        r'\b7a\b[^\n]*Gross amount from sales of assets other than inventory',
        r'\b7a\b[^\n]*Gross amount from sale',
        r'\b7a\b[^\n]*sales of assets other than inventory',
        r'Gross amount from sales? of assets other than inventory[^\n]*7a',
        r'\b7a\b[^\n]*assets other than inventory',
    ]

    for pattern in patterns:
        # Try to find the row
        match = re.search(pattern, section, re.IGNORECASE)
        if match:
            # Get the matched line and next few lines (for multi-line values)
            start = match.start()
            end = match.end()
            extended_text = section[start:end+300]  # Get next 300 chars

            # Extract all monetary amounts
            amounts = field_extractor._find_amounts_in_text(extended_text)

            if amounts:
                # Return first two values (Securities, Other)
                securities = amounts[0] if len(amounts) >= 1 else None
                other = amounts[1] if len(amounts) >= 2 else None

                # Validate that these look like valid amounts (not row numbers)
                if securities and len(securities.replace(',', '').replace('.', '')) >= 4:
                    return (securities, other)

    # Last resort: Look for row 7a with column headers
    # (i) Securities and (ii) Other
    match_7a = re.search(r'\b7a\b', section, re.IGNORECASE)
    if match_7a:
        # Look within next 500 characters for values
        window = section[match_7a.start():match_7a.start()+500]

        # Try to find (i) Securities and (ii) Other columns
        securities_match = re.search(r'\(i\)\s*Securities[^\n]*', window, re.IGNORECASE)
        if securities_match:
            securities_line = securities_match.group(0)
            # Get amounts from next few lines
            remaining = window[securities_match.end():]
            amounts = field_extractor._find_amounts_in_text(remaining[:200])
            if amounts:
                return (amounts[0] if len(amounts) >= 1 else None,
                        amounts[1] if len(amounts) >= 2 else None)

    return (None, None)


def extract_total_revenue_enhanced(section: str, field_extractor) -> Optional[str]:
    """
    Enhanced extraction for Row 12 Total Revenue
    Avoids matching years like "2024"
    """
    # Try specific patterns that avoid year confusion
    patterns = [
        # Pattern 1: Row 12 followed by "Total revenue"
        r'\b12\b[^\d]*Total revenue[^\n]*',
        # Pattern 2: "Total revenue" with explicit row marker
        r'Total revenue[^\n]*\b12\b',
        # Pattern 3: "Total revenue" near "See instructions" or "line 12"
        r'Total revenue[^\n]*(?:See instructions|line 12)',
        # Pattern 4: Just "12" and "Total revenue" with some context
        r'(?:Row|Line)?\s*12[^\d]*Total revenue',
    ]

    for pattern in patterns:
        match = re.search(pattern, section, re.IGNORECASE)
        if match:
            # Get the line and next few lines
            matched_text = match.group(0)
            start = match.start()
            end = match.end()
            extended = section[start:end+200]

            # Find amounts
            amounts = field_extractor._find_amounts_in_text(extended)

            for amount in amounts:
                # Skip if it looks like a year (exactly 4 digits, starts with 19 or 20)
                clean = amount.replace(',', '').replace('.', '')
                if len(clean) == 4 and (clean.startswith('19') or clean.startswith('20')):
                    continue

                # Valid amount should be longer or have commas
                if len(clean) >= 5 or ',' in amount:
                    return amount

    return None


def extract_page1_enhanced(text: str, field_extractor) -> dict:
    """
    Enhanced extraction for Page 1 fields
    Handles fragmented text in 2022-style PDFs
    """
    enhancements = {}

    # Special handling for 2022-style PDFs where values appear in a summary table
    # before the row labels
    summary_table_match = re.search(
        r'Prior Year\s+Current Year(.*?)(?:Grants and similar|Benefits paid)',
        text, re.DOTALL | re.IGNORECASE
    )

    if summary_table_match:
        # Extract from summary table format
        table_text = summary_table_match.group(1)
        lines = table_text.split('\n')

        # Parse the table - usually has paired values (Prior Year, Current Year)
        amounts = []
        for line in lines:
            line_amounts = field_extractor._find_amounts_in_text(line)
            if line_amounts:
                amounts.extend(line_amounts)

        # Map amounts to fields based on typical Form 990 order
        # Row 8: Contributions (usually 1st pair)
        if len(amounts) >= 2:
            enhancements['total_contributions'] = amounts[1]  # Current Year

        # Row 12: Total revenue (usually 5th value for Current Year in sequence)
        # Look for the largest value which is usually total revenue
        current_year_amounts = [amounts[i] for i in range(1, len(amounts), 2) if i < len(amounts)]
        if current_year_amounts:
            # Find the line with "Total revenue"
            for i, line in enumerate(lines):
                if 'Total revenue' in line or 'Total revenue-add' in line:
                    # Get amounts from nearby lines
                    nearby_text = '\n'.join(lines[max(0,i-5):i+5])
                    nearby_amounts = field_extractor._find_amounts_in_text(nearby_text)
                    if nearby_amounts:
                        # Current Year is usually the second value or last value
                        enhancements['total_revenue'] = nearby_amounts[-1] if len(nearby_amounts) % 2 == 1 else nearby_amounts[-1]
                        break

    # Find Part I Summary section
    part1_match = re.search(
        r'Part\s+I\s+Summary(.*?)(?:Part\s+II|Statement of Program Service)',
        text, re.DOTALL | re.IGNORECASE
    )

    if not part1_match:
        # Try alternative: Look for row 8-22 which are Page 1 rows
        part1_match = re.search(
            r'(?:Contributions and grants|Row 8)(.*?)(?:Part\s+II|Part\s+III)',
            text, re.DOTALL | re.IGNORECASE
        )

    section = part1_match.group(1) if part1_match else text[:10000]  # Increased window

    # Enhanced patterns for commonly missed fields

    # Row 8: Total contributions (with Prior Year / Current Year columns)
    row8_patterns = [
        r'(?:8|Row 8|Line 8)[^\n]*(?:Contributions and grants|Total contributions)[^\n]*',
        r'Contributions and grants[^\n]*(?:\bline 1h\b|\b8\b)',
    ]

    for pattern in row8_patterns:
        match = re.search(pattern, section, re.IGNORECASE)
        if match:
            extended = section[match.start():match.start()+500]
            amounts = field_extractor._find_amounts_in_text(extended)

            # Often there are two columns: Prior Year and Current Year
            # We want Current Year (usually the last/rightmost value)
            if amounts:
                enhancements['total_contributions'] = amounts[-1]  # Last value = Current Year
                break

    # Row 12: Total revenue
    enhancements['total_revenue'] = extract_total_revenue_enhanced(section, field_extractor)

    # Row 20: Total assets
    # In 2022-style PDFs, format is: value1\nvalue2\nTotal assets
    # Where value1 = Beginning, value2 = End of Year (what we want)
    assets_match = re.search(
        r'(\d{1,3}(?:,\d{3})+)\s*[\n\r]+\s*(\d{1,3}(?:,\d{3})+)\s*[\n\r]+\s*Total assets',
        text, re.IGNORECASE
    )
    if assets_match:
        # Second value is End of Year
        enhancements['total_assets'] = assets_match.group(2)

    if not enhancements.get('total_assets'):
        row20_patterns = [
            r'(?:20|Row 20|Line 20)[^\n]*Total assets[^\n]*',
            r'Total assets[^\n]*(?:\bline 16\b|\b20\b)',
        ]

        for pattern in row20_patterns:
            match = re.search(pattern, section, re.IGNORECASE)
            if match:
                extended = section[match.start():match.start()+500]
                amounts = field_extractor._find_amounts_in_text(extended)
                if amounts:
                    # Filter out years
                    valid_amounts = [a for a in amounts
                                    if not (len(a.replace(',','').replace('.','')) == 4
                                           and a.replace(',','').replace('.','').startswith(('19','20')))]
                    if valid_amounts:
                        enhancements['total_assets'] = valid_amounts[-1]
                        break

    # Row 21: Total liabilities
    # Values appear BEFORE the label in 2022-style PDFs
    if not enhancements.get('total_liabilities'):
        # Look for pattern: amounts -> "Total liabilities"
        liab_match = re.search(
            r'((?:\d{1,3}(?:,\d{3})+\s*){1,2})Total liabilities',
            text, re.IGNORECASE
        )
        if liab_match:
            liab_amounts = field_extractor._find_amounts_in_text(liab_match.group(1))
            if liab_amounts:
                # End of Year value is the second value or the only value
                enhancements['total_liabilities'] = liab_amounts[1] if len(liab_amounts) >= 2 else liab_amounts[0]

    if not enhancements.get('total_liabilities'):
        row21_patterns = [
            r'(?:21|Row 21|Line 21)[^\n]*Total liabilities[^\n]*',
            r'Total liabilities[^\n]*(?:\b21\b|\bline 21\b)',
        ]

        for pattern in row21_patterns:
            match = re.search(pattern, section, re.IGNORECASE)
            if match:
                extended = section[match.start():match.start()+500]
                amounts = field_extractor._find_amounts_in_text(extended)
                if amounts:
                    valid_amounts = [a for a in amounts
                                    if not (len(a.replace(',','').replace('.','')) == 4
                                           and a.replace(',','').replace('.','').startswith(('19','20')))]
                    if valid_amounts:
                        enhancements['total_liabilities'] = valid_amounts[-1]
                        break

    # Row 22: Net assets
    # In 2022-style PDFs, format is: value1\nvalue2\n[possible OCR junk]\nNet assets or fund balances
    if not enhancements.get('net_assets_or_fund_balances'):
        # Allow up to 200 characters of junk between values and label
        net_match = re.search(
            r'(\d{1,3}(?:,\d{3})+)\s*[\n\r]+\s*(\d{1,3}(?:,\d{3})+)[\s\S]{0,200}?Net assets or fund balances',
            text, re.IGNORECASE
        )
        if net_match:
            # Second value is End of Year
            enhancements['net_assets_or_fund_balances'] = net_match.group(2)

    if not enhancements.get('net_assets_or_fund_balances'):
        row22_patterns = [
            r'(?:22|Row 22|Line 22)[^\n]*Net assets[^\n]*',
            r'Net assets.*fund balances[^\n]*(?:\b22\b|\bline 22\b)',
        ]

        for pattern in row22_patterns:
            match = re.search(pattern, section, re.IGNORECASE)
            if match:
                extended = section[match.start():match.start()+500]
                amounts = field_extractor._find_amounts_in_text(extended)
                if amounts:
                    valid_amounts = [a for a in amounts
                                    if not (len(a.replace(',','').replace('.','')) == 4
                                           and a.replace(',','').replace('.','').startswith(('19','20')))]
                    if valid_amounts:
                        enhancements['net_assets_or_fund_balances'] = valid_amounts[-1]
                        break

    return enhancements


def extract_part8_enhanced(section: str, field_extractor) -> dict:
    """
    Enhanced extraction for Part VIII fields
    Handles all commonly missed fields
    """
    enhancements = {}

    # Row 7a: Gross sales (Securities vs Other)
    securities, other = extract_row_7a_enhanced(section, field_extractor)
    if securities:
        enhancements['gross_sales_securities'] = securities
    if other:
        enhancements['gross_sales_other'] = other

    # Row 12: Total revenue (avoid extracting year)
    total_rev = extract_total_revenue_enhanced(section, field_extractor)
    if total_rev:
        enhancements['total_revenue'] = total_rev

    # Row 1h: Contributions total (often formatted as "Total. Add lines 1a-1f")
    row1h_patterns = [
        r'\b1h\b[^\n]*Total[^\n]*(?:Add lines 1a|lines 1a-1f)',
        r'Total[^\n]*Add lines 1a[^\n]*\b1h\b',
        r'\bh\b[^\n]*Total[^\n]*Add lines 1a',
    ]

    for pattern in row1h_patterns:
        match = re.search(pattern, section, re.IGNORECASE)
        if match:
            extended = section[match.start():match.start()+300]
            amounts = field_extractor._find_amounts_in_text(extended)
            if amounts:
                enhancements['contributions_total'] = amounts[0]
                break

    # Row 2g: Program service revenue total
    row2g_patterns = [
        r'\b2g\b[^\n]*Total[^\n]*(?:Add lines 2a|program service revenue)',
        r'Total[^\n]*(?:Add lines 2a|program service revenue)[^\n]*\b2g\b',
        r'\bg\b[^\n]*Total[^\n]*Add lines 2a',
    ]

    for pattern in row2g_patterns:
        match = re.search(pattern, section, re.IGNORECASE)
        if match:
            extended = section[match.start():match.start()+300]
            amounts = field_extractor._find_amounts_in_text(extended)
            if amounts:
                enhancements['program_service_revenue_total'] = amounts[0]
                break

    return enhancements
