"""
Precise Field Extraction Fixes
Addresses specific accuracy issues where patterns match wrong rows
"""
import re
from typing import Optional, List


def extract_gross_receipts_precise(text: str, field_extractor) -> Optional[str]:
    """
    More precise Gross Receipts extraction
    Avoids matching partial values like "100,000"
    Handles both normal and reversed layouts
    """
    # Pattern 1: Reversed layout - amount BEFORE label (2024 PDF format)
    # Look for: substantial amount, then "G Gross receipts $" within next 50 chars
    match = re.search(r'([\d,]+\.?)\s*[\n\r]+\s*G\s+Gross\s+receipts\s*\$', text, re.IGNORECASE)
    if match:
        amount = match.group(1).rstrip('.')
        clean = amount.replace(',', '')
        if len(clean) >= 5:  # At least 5 digits (filters out small amounts)
            return amount

    # Pattern 2: "G Gross receipts $" with amount (for header format)
    match = re.search(r'\bG\s+Gross\s+receipts\s*\$\s*([\d,]+)', text, re.IGNORECASE)
    if match:
        amount = match.group(1)
        # Validate it's a substantial amount (gross receipts are usually large)
        clean = amount.replace(',', '')
        if len(clean) >= 5:  # At least 5 digits
            return amount

    # Pattern 3: "Gross receipts $" with amount
    match = re.search(r'Gross\s+receipts\s*\$\s*([\d,]+)', text, re.IGNORECASE)
    if match:
        amount = match.group(1)
        if field_extractor._is_valid_monetary_amount(amount):
            return amount

    return None


def extract_row1_contributions_precise(section: str, field_extractor) -> dict:
    """
    Precise extraction for Row 1 (Contributions breakdown)
    Handles cases where values are on separate lines from labels
    Handles reversed layouts (2024 PDF style)
    """
    results = {}

    # Row 1f: All other contributions
    # 2019 PDF: "f  All other contributions...\n...\n1f  36,569,028"
    # 2024 PDF: "All other contributions...~ value.\n1f"
    patterns_1f = [
        r'All other contributions[^\n]*?~\s*([\d,]+)\.\s*[\n\r]+\s*1f',  # 2024 PDF: amount ~ value. \n 1f
        r'All other contributions[^\n\d]*?[\n\r]+[^\n]*?[\n\r]+\s*1f\s+([\d,]+)',  # 2019: label \n text \n 1f amount
        r'\b1f\b[^\n]*All other contributions[^\n]*?([\d,]+)',
        r'\bf\b\s+All other contributions[^\n]*?([\d,]+)',
        r'All other contributions[^\n]*?(?:\b1f\b|\bf\b)[^\n]*?([\d,]+)',
    ]
    for pattern in patterns_1f:
        match = re.search(pattern, section, re.IGNORECASE)
        if match:
            results['all_other_contributions'] = match.group(1).rstrip('.')
            break

    # Row 1g: Noncash contributions
    # IMPORTANT: Must match "1g" specifically, not "1f"!
    # 2024 PDF format: "$ 16,924." on previous line, then "g Noncash contributions ... 1g"
    patterns_1g = [
        r'\$\s*([\d,]+)\.\s*[\n\r]+\s*g\s+Noncash contributions',  # Reversed: $ amount \n g Noncash
        r'\b1g\b[^\n]*Noncash contributions[^\n]*?([\d,]+)',
        r'\bg\b\s+Noncash contributions[^\n]*?([\d,]+)',
        r'Noncash contributions.*?\b1g\b[^\n]*?([\d,]+)',
    ]
    for pattern in patterns_1g:
        match = re.search(pattern, section, re.IGNORECASE)
        if match:
            value = match.group(1).rstrip('.')
            # Double-check it's not the same as 1f value
            if value != results.get('all_other_contributions'):
                results['noncash_contributions'] = value
                break

    # Row 1h: Total. Add lines 1a-1f
    # 2024 PDF format: "Total. Add lines 1a-1f  384,948." then "h" on next line
    # 2019 PDF format: "h  Total. Add lines 1a–1f . . . (cid:97) 43,437,498" (en-dash + OCR artifact)
    # Look for amounts with commas (e.g., "43,437,498") to skip OCR artifacts like "(cid:97)"
    patterns_1h = [
        r'Total[^\n]*Add lines 1a[\-–]1f[^\n]*?([\d,]+)\.',  # With period (2024)
        r'\b1h\b[^\n]*Total[^\n]*Add lines 1a[^\n]*?([\d,]+)',
        r'\bh\b\s+Total[^\n]*Add lines 1a[\-–]1f[^\n]*?(\d+,\d{3},\d{3})',  # 2019: XX,XXX,XXX format
        r'Total[^\n]*Add lines 1a[\-–]1f[^\n]*(\d{1,3}(?:,\d{3})+)',  # Amount with commas
    ]
    for pattern in patterns_1h:
        match = re.search(pattern, section, re.IGNORECASE)
        if match:
            results['contributions_total'] = match.group(1).rstrip('.')
            break

    return results


def extract_row2g_program_revenue_precise(section: str, field_extractor) -> Optional[str]:
    """
    Precise extraction for Row 2g (Program service revenue total)
    2019 PDF format: "g \nTotal. Add lines 2a–2f . . . (cid:97) 84,415,118" (en-dash + OCR artifact)
    """
    # Look for: "2g" OR "g Total. Add lines 2a-2f" (accept both - and –)
    # Strategy: Find the line, then extract all large amounts from it (to avoid OCR artifacts)
    patterns = [
        r'\b2g\b[^\n]*Total[^\n]*Add lines 2a[^\n]+',
        r'\bg\b\s+[\n\r]?\s*Total[^\n]*Add lines 2a[\-–]2[a-z][^\n]+',  # Allow newline
        r'Total[^\n]*Add lines 2a[\-–]2[a-z][^\n]+',  # Match the line
    ]

    for pattern in patterns:
        match = re.search(pattern, section, re.IGNORECASE)
        if match:
            line = match.group(0)
            # Find all properly formatted amounts (with commas) on this line
            amounts = re.findall(r'(\d{1,3}(?:,\d{3})+)', line)
            if amounts:
                # Return the largest amount (avoids OCR artifacts which are usually small)
                return max(amounts, key=lambda x: int(x.replace(',', '')))

    return None


def extract_row5_royalties_precise(section: str, field_extractor) -> Optional[str]:
    """
    Precise extraction for Row 5 (Royalties)
    Must NOT match Row 6a!
    2019 PDF format: "5  Royalties  . . . (cid:97) 404,973 0 0 404,973"
    2024 PDF format: "Royalties [fill chars]\n5\n" with no value
    """
    # Pattern 1: Row 5 followed by "Royalties" on same line (2019 format)
    # 2019: "5  Royalties  . . . (cid:97) 404,973 0 0 404,973"
    # Use \D to ensure we start at the beginning of a number (not in the middle)
    # Must NOT have "6" nearby
    pattern = r'\b5\b[^\d\n]*Royalties[^\n]*\D(\d{1,3}(?:,\d{3})+)'  # Start after non-digit
    match = re.search(pattern, section, re.IGNORECASE)
    if match:
        amount = match.group(1)
        # Verify it's not crossing into Row 6
        context = section[match.start():match.end()]
        if '6' not in context and 'Gross rents' not in context:
            return amount.rstrip('.')

    # Pattern 2: 2024 PDF format - "Royalties" then newline then "5" then newline
    match = re.search(r'Royalties[^\n]*[\n\r]+\s*5\s*[\n\r]', section, re.IGNORECASE)
    if match:
        # Row 5 exists, now check if there's a value nearby
        # Get text in a small window (150 chars after "Royalties")
        start = match.start()
        window = section[start:start+150]

        # Look for amount on the same line as "Royalties" (before the newline)
        # Must not cross into Row 6
        value_match = re.search(r'Royalties[^\n]*?([\d,]+)', window, re.IGNORECASE)
        if value_match:
            # Make sure we didn't cross into Row 6
            text_before_value = window[:value_match.end()]
            # Check if "5" appears before the value (means value is after Row 5 label)
            # And check we haven't hit Row 6 markers
            if '\n5\n' in text_before_value[:value_match.start()] and '6' not in text_before_value[value_match.start():value_match.end()] and 'Gross rents' not in text_before_value:
                return value_match.group(1).rstrip('.')

        # Row exists but no value - return empty string to indicate field is present but empty
        return ''

    return None


def extract_part8_total_revenue_precise(section: str, field_extractor) -> Optional[str]:
    """
    Precise extraction for Row 12 (Total revenue)
    Must get the FINAL total, not intermediate values
    """
    # Look for Row 12 specifically
    patterns = [
        r'\b12\b[^\n]*Total revenue[^\n]*?([\d,]+)',
        r'Total revenue[^\n]*\b12\b[^\n]*?([\d,]+)',
        r'\b12\b[^\n]*Total revenue.*?See instructions[^\n]*?([\d,]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, section, re.IGNORECASE)
        if match:
            amount = match.group(1)
            # Filter out years and small numbers
            clean = amount.replace(',', '')
            if len(clean) >= 5:  # Total revenue should be substantial
                # Make sure it's not a year
                if not (len(clean) == 4 and clean.startswith(('19', '20'))):
                    return amount

    return None


def extract_part9_professional_fundraising_precise(section: str, field_extractor) -> Optional[str]:
    """
    Precise extraction for Part IX Row 11e (Professional fundraising services)
    Must match ONLY Row 11e, not other rows (especially not 11f which follows)
    Handles 2024 PDF format where row label is on separate line
    """
    # 2024 PDF format: "Professional fundraising services. See Part IV, line 17\ne\n" with no value
    # Then Row 11f starts: "Investment management fees~~~~~~~~ 78,097."

    # Look for Row 11e
    match = re.search(r'Professional fundraising services[^\n]*[\n\r]+\s*e\s*[\n\r]', section, re.IGNORECASE)
    if match:
        # Row 11e found, now check if there's a value BEFORE Row 11f starts
        start = match.start()
        # Get small window after "Professional fundraising services"
        window = section[start:start+200]

        # Look for amount that's NOT after "f" or "Investment" (which would be Row 11f)
        before_next_row = window.split('\nf\n')[0] if '\nf\n' in window else window.split('Investment')[0] if 'Investment' in window else window

        # Search for amount in this limited window
        amount_match = re.search(r'([\d,]+)', before_next_row)
        if amount_match and 'e' in before_next_row[:amount_match.start()]:
            return amount_match.group(1).rstrip('.')

        # Row exists but no value - return empty string
        return ''

    # Try standard pattern as fallback
    pattern = r'\b11\s*e\b[^\n]*Professional fundraising[^\n]*?([\d,]+)'
    match = re.search(pattern, section, re.IGNORECASE)

    if match:
        amount = match.group(1)
        return amount.rstrip('.')

    return None


def extract_part9_affiliate_payments_precise(section: str, field_extractor) -> Optional[str]:
    """
    Precise extraction for Part IX Row 21 (Payments to affiliates)
    Must match ONLY Row 21, not other rows (especially not Row 22 which follows)
    Handles 2024 PDF format where row may have no value
    """
    # 2024 PDF format: "Payments to affiliates ~~~~~~~~~~~~\n21\n" with no value
    # Then Row 22 starts: "Depreciation, depletion, and amortization ~~ 112,815."

    # Look for Row 21 with Payments to affiliates
    match = re.search(r'Payments to affiliates[^\n]*[\n\r]+\s*21\s*[\n\r]', section, re.IGNORECASE)
    if match:
        # Row 21 found, check if there's a value BEFORE Row 22 starts
        start = match.start()
        window = section[start:start+200]

        # Look for amount that's NOT after "22" or "Depreciation" (which would be Row 22)
        before_next_row = window.split('\n22\n')[0] if '\n22\n' in window else window.split('Depreciation')[0] if 'Depreciation' in window else window

        # Search for amount in this limited window
        amount_match = re.search(r'([\d,]+)', before_next_row)
        if amount_match and '21' in before_next_row[:amount_match.start()]:
            return amount_match.group(1).rstrip('.')

        # Row exists but no value - return empty string
        return ''

    # Try standard pattern as fallback
    pattern = r'\b21\b[^\n]*Payments to affiliates[^\n]*?([\d,]+)'
    match = re.search(pattern, section, re.IGNORECASE)

    if match:
        amount = match.group(1)
        return amount.rstrip('.')

    return None


def apply_precise_fixes(page1_fields, part8_fields, part9_fields, full_text, field_extractor) -> None:
    """
    Apply all precise fixes to the extracted fields
    Modifies fields in-place
    """
    # Fix Gross Receipts
    precise_gross_receipts = extract_gross_receipts_precise(full_text, field_extractor)
    if precise_gross_receipts:
        page1_fields.gross_receipts = precise_gross_receipts

    # Extract Part VIII section
    part8_match = re.search(
        r'Part VIII\s+Statement of Revenue(.*?)(?:Part IX\s+Statement of Functional|$)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    part8_section = part8_match.group(1) if part8_match else full_text

    # Fix Row 1 contributions
    row1_fixes = extract_row1_contributions_precise(part8_section, field_extractor)
    if row1_fixes.get('all_other_contributions'):
        part8_fields.all_other_contributions = row1_fixes['all_other_contributions']
    if row1_fixes.get('noncash_contributions'):
        part8_fields.noncash_contributions = row1_fixes['noncash_contributions']
    if row1_fixes.get('contributions_total'):
        part8_fields.contributions_total = row1_fixes['contributions_total']

    # Fix Row 2g program service revenue
    precise_2g = extract_row2g_program_revenue_precise(part8_section, field_extractor)
    if precise_2g:
        part8_fields.program_service_revenue_total = precise_2g

    # Fix Row 5 royalties (to avoid matching Row 6a)
    precise_royalties = extract_row5_royalties_precise(part8_section, field_extractor)
    if precise_royalties is not None:  # Could be None (empty) or a value
        part8_fields.royalties = precise_royalties

    # Fix Row 12 total revenue
    precise_total_rev = extract_part8_total_revenue_precise(part8_section, field_extractor)
    if precise_total_rev:
        part8_fields.total_revenue = precise_total_rev

    # Extract Part IX section
    part9_match = re.search(
        r'Part IX\s+Statement of Functional(.*?)(?:Part X\s|$)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    part9_section = part9_match.group(1) if part9_match else full_text

    # Fix Part IX Row 11e professional fundraising
    precise_11e = extract_part9_professional_fundraising_precise(part9_section, field_extractor)
    if precise_11e is not None:  # Update even if empty string (field exists but no value)
        part9_fields.professional_fundraising_services = precise_11e

    # Fix Part IX Row 21 affiliate payments
    precise_21 = extract_part9_affiliate_payments_precise(part9_section, field_extractor)
    if precise_21 is not None:  # Update even if empty string (field exists but no value)
        part9_fields.affiliate_payments = precise_21
