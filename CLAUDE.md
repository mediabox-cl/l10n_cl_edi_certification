# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Odoo module (`l10n_cl_edi_certification`) that facilitates the official certification process with Chile's SII (Servicio de Impuestos Internos) for electronic invoicing. The module builds on top of the existing `l10n_cl_edi` module and provides tools to automate the tedious certification process using real SII-provided CAFs and test sets.

## Core Architecture

### Key Models and Their Relationships

**Main Process Controller:**
- `CertificationProcess` (`models/certification_process.py`) - Central hub that manages the entire certification workflow

**Document Generation Flow:**
- `ParsedSet` → `CaseDTE` → `DocumentGenerator` → `account.move` (invoice)
- `CertificationDocumentGenerator` (`models/certification_document_generator.py`) - Handles document creation using sale.order → invoice flow to avoid rating mixin issues

**IECV Book Generation:**
- `CertificationIecvBook` (`models/certification_iecv_book.py`) - Generates purchase/sales books required for certification
- Separate processors for sales (`certification_iecv_sales_processor.py`) and purchases (`certification_iecv_purchase_processor.py`)

**Data Parser:**
- `SiiTestSetParser` (`tools/sii_test_set_parser.py`) - Parses SII test set files (.txt format) and extracts test cases

### Process States

The certification process follows this state machine:
1. `preparation` - Initial setup (company data, certificates, journals)
2. `configuration` - Load test sets and verify real CAFs provided by SII
3. `generation` - Generate test documents using real CAFs
4. `completed` - All documents generated and books created

### Key Design Patterns

**Partner Management:**
- **Fixed Architecture:** No longer uses a single SII partner (60803000-K) for all documents
- Each DTE uses a unique certification partner from pre-loaded partner pool
- Partners loaded from `data/certification_partners.xml`

**Document Generation:**
- Uses sale.order → invoice flow instead of direct invoice creation
- Avoids rating mixin conflicts through proper workflow
- Each case generates one document with proper references
- Uses real CAFs provided by SII for official certification

**Status Synchronization:**
- Automatic recovery of lost relationships between cases and invoices
- Real-time status verification when opening records

## Deployment Workflow

### Proper Module Update Process
The correct way to update this module is:
1. Commit changes to git
2. Pull changes on the server
3. Restart Odoo server
4. Update module through Odoo's App Manager (not terminal commands)

**Important:** Terminal commands like `python odoo-bin -u module_name` do not work reliably. Always use the App Manager interface for module updates.

### Testing the Parser
```bash
# Test the parser directly with SII test sets
python tools/sii_test_set_parser.py examples/SIISetDePruebas762352915\ -\ 03.txt
```

**Note:** The examples/ directory contains the actual SII test sets. Use the latest one (currently 03) for certification work.

## Important File Locations

### Configuration and Data
- `__manifest__.py` - Module definition and dependencies
- `data/certification_partners.xml` - Pre-loaded certification partners
- `data/l10n_cl_edi_certification_data.xml` - Base configuration data
- `security/ir.model.access.csv` - Access rights configuration

### Views and UI
- `views/certification_process_view.xml` - Main certification dashboard
- `views/test_set_views.xml` - Views for parsed test sets and cases
- `wizard/iecv_generator_wizard_view.xml` - IECV book generation wizard

### Core Logic
- `models/certification_process.py` - Main process controller (1000+ lines)
- `models/certification_document_generator.py` - Document creation logic using real CAFs
- `models/certification_case_dte.py` - Individual test case handling

## Dependencies

**Required Odoo Modules:**
- `account` - Accounting framework
- `l10n_cl` - Chile localization  
- `l10n_cl_edi` - Chile electronic invoicing (base module)

**Python Dependencies:**
- `lxml` - XML parsing for test sets and DTE generation
- Standard library modules (no external pip requirements)

## Common Development Patterns

### Adding New Document Types
1. Update `SiiTestSetParser` to recognize the new document type
2. Add mapping in `_normalize_document_type()` method
3. Update `CertificationDocumentGenerator` to handle the new type
4. Ensure proper real CAF validation in `CertificationProcess`

### Debugging Generation Issues
1. Check `_recover_lost_relationships()` in certification_process.py:1100+
2. Verify case status with `_sync_generation_status()` 
3. Look for errors in `CertificationDocumentGenerator.generate_document()`
4. Check partner assignment and journal configuration

### IECV Book Customization
1. Modify processors in `models/certification_iecv_*_processor.py`
2. Update XML templates in `certification_iecv_xml_builder.py`
3. Test with different document combinations

## Known Issues and Limitations

- Requires real CAFs provided by SII for certification
- Some SII test formats may need parser updates
- IECV books limited to current Chilean tax regulations

## Important Notes

**SIIDEMO is NOT used:** This module is specifically for real SII certification process only. Any SIIDEMO functionality is used only for testing unrelated features and is not part of the certification scope. Demo CAFs are not created or used - only real CAFs provided by SII.

## Testing Strategy

1. Use the SII test sets in `examples/` directory (use the latest: 03)
2. Ensure real CAFs are loaded from SII
3. Verify each process state transition
4. Check generated documents match SII requirements
5. Validate IECV books contain all required elements
6. Test through proper deployment workflow (commit → pull → restart → update via App Manager)

## Tool Usage Guidelines for Claude Code

### File System Access
**Current Project Files:** Use standard tools (Read, Edit, MultiEdit, Write, Glob, Grep) for working with files in the current project directory `/home/butcherwutcher/projects/l10n_cl_edi_certification/`.

**External Reference Files:** Use `mcp__filesystem__*` tools ONLY when exploring files outside the VSCode working directory, such as:
- `odoo_test/` - Contains Odoo's base EDI modules for reference on implementation patterns
- Other external directories for understanding base Odoo functionality

### Memory Management with mnemox-lite
**Project ID:** `74834324-ed6e-4179-8d6c-86ee03729458`

**Storing Information:**
```
mcp__mnemox-lite__remember with project_id and comprehensive content
```
- Store insights, decisions, and tasks in natural language
- Provide complete context in single requests rather than chunking
- Let the memory system handle division and storage automatically

**Retrieving Information:**
```
mcp__mnemox-lite__recall with project_id and specific queries
```
- Use natural language queries to retrieve relevant information
- Focus queries on specific aspects (architecture, decisions, issues, etc.)

**Important:** Always store new insights, architectural decisions, bug fixes, and task completions in memory for future reference.

## Odoo Version Compatibility Notes

### Modern Odoo Syntax (17.0+)
When working with views and fields, use these modern patterns:

**View Types:**
- Use `<list>` instead of `<tree>` for list views
- Update view names accordingly (e.g., `model.list` instead of `model.tree`)
- Update action `view_mode` from `tree,form` to `list,form`

**Field Visibility:**
- Use `invisible="condition"` instead of `attrs="{'invisible': [condition]}"`
- Use `readonly="condition"` instead of `attrs="{'readonly': [condition]}"`

**Field Tracking:**
- Remove `tracking=True` or `track_visibility='onchange'` parameters unless model inherits from `mail.thread`
- These parameters cause warnings in newer Odoo versions and are not needed for certification modules

**Example Migration:**
```xml
<!-- Old syntax -->
<tree>
    <field name="name" attrs="{'invisible': [('state', '=', 'draft')]}"/>
</tree>

<!-- New syntax -->
<list>
    <field name="name" invisible="state == 'draft'"/>
</list>
```

## Architecture Notes

The module follows Odoo best practices with:
- Proper model inheritance and relationships
- Computed fields with dependencies
- State machine implementation
- Real certification workflow with SII-provided CAFs
- Comprehensive logging for debugging
- Wizard patterns for complex operations
- Modern Odoo syntax compatibility