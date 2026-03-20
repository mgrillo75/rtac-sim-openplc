# Development Plan: OPC-UA TIME Type Support

## Executive Summary

The current OPC-UA plugin implementation does not support IEC 61131-3 TIME type variables. This document outlines the development and test plan to introduce TIME type support.

## Current State Analysis

### IEC 61131-3 TIME Structure (from `core/src/lib/iec_types.h`)

```c
typedef struct {
    int32_t tv_sec;   // Seconds
    int32_t tv_nsec;  // Nanoseconds
} IEC_TIMESPEC;

typedef IEC_TIMESPEC IEC_TIME;   // Duration type
typedef IEC_TIMESPEC IEC_DATE;   // Date type
typedef IEC_TIMESPEC IEC_DT;     // Date and Time type
typedef IEC_TIMESPEC IEC_TOD;    // Time of Day type
```

**Key characteristics:**
- Total size: 8 bytes
- Represents duration/time as seconds + nanoseconds
- Same underlying structure for TIME, DATE, DT, and TOD

### Current Type Support (from `opcua_utils.py`)

| PLC Type | OPC-UA Type | Size |
|----------|-------------|------|
| BOOL | Boolean | 1 byte |
| BYTE | Byte | 1 byte |
| INT | Int16 | 2 bytes |
| DINT/INT32 | Int32 | 4 bytes |
| LINT | Int64 | 8 bytes |
| FLOAT/REAL | Float | 4 bytes |
| STRING | String | 127 bytes |

**Missing types:** TIME, DATE, TOD, DT, LREAL, WORD, DWORD, LWORD, UINT, UDINT, ULINT, SINT, USINT

### Gap Analysis

1. **Type Mapping**: `map_plc_to_opcua_type()` has no TIME mapping
2. **Memory Access**: `opcua_memory.py` reads 8-byte values as `c_uint64`, not as TIME struct
3. **Value Conversion**: `convert_value_for_opcua()` and `convert_value_for_plc()` have no TIME handling
4. **Configuration**: No TIME examples in config templates or documentation

---

## Development Plan

### Phase 1: Core Type Support

#### Task 1.1: Define IEC_TIMESPEC ctypes Structure

**File:** `core/src/drivers/plugins/python/opcua/opcua_memory.py`

Add a ctypes structure matching the C definition:

```python
class IEC_TIMESPEC(ctypes.Structure):
    """
    ctypes structure matching IEC_TIMESPEC from iec_types.h.

    typedef struct {
        int32_t tv_sec;   // Seconds
        int32_t tv_nsec;  // Nanoseconds
    } IEC_TIMESPEC;
    """
    _fields_ = [
        ("tv_sec", ctypes.c_int32),
        ("tv_nsec", ctypes.c_int32),
    ]

TIMESPEC_SIZE = 8  # sizeof(IEC_TIMESPEC)
```

#### Task 1.2: Add TIME Type Mapping

**File:** `core/src/drivers/plugins/python/opcua/opcua_utils.py`

Update `map_plc_to_opcua_type()`:

```python
def map_plc_to_opcua_type(plc_type: str) -> ua.VariantType:
    """Map plc datatype to OPC-UA VariantType."""
    type_mapping = {
        # Existing types...
        "BOOL": ua.VariantType.Boolean,
        "BYTE": ua.VariantType.Byte,
        "INT": ua.VariantType.Int16,
        "INT32": ua.VariantType.Int32,
        "DINT": ua.VariantType.Int32,
        "LINT": ua.VariantType.Int64,
        "FLOAT": ua.VariantType.Float,
        "REAL": ua.VariantType.Float,
        "STRING": ua.VariantType.String,
        # New TIME types - represented as Int64 (milliseconds)
        "TIME": ua.VariantType.Int64,
        "DATE": ua.VariantType.DateTime,
        "TOD": ua.VariantType.Int64,  # Milliseconds since midnight
        "DT": ua.VariantType.DateTime,
    }
    return type_mapping.get(plc_type.upper(), ua.VariantType.Variant)
```

**Design Decision: TIME Representation in OPC-UA**

| Option | OPC-UA Type | Pros | Cons |
|--------|-------------|------|------|
| A. Int64 (ms) | Int64 | Simple, standard duration format | Loss of nanosecond precision |
| B. Double (seconds) | Double | Good precision, human readable | Floating point quirks |
| C. Custom Struct | ExtensionObject | Full precision preserved | Complex, non-standard |

**Recommendation:** Option A (Int64 milliseconds) for TIME/TOD types, and DateTime for DATE/DT types.

#### Task 1.3: Implement TIME Conversion Functions

**File:** `core/src/drivers/plugins/python/opcua/opcua_utils.py`

```python
def timespec_to_milliseconds(tv_sec: int, tv_nsec: int) -> int:
    """Convert IEC_TIMESPEC to milliseconds."""
    return (tv_sec * 1000) + (tv_nsec // 1_000_000)

def milliseconds_to_timespec(ms: int) -> tuple[int, int]:
    """Convert milliseconds to (tv_sec, tv_nsec) tuple."""
    tv_sec = ms // 1000
    tv_nsec = (ms % 1000) * 1_000_000
    return (tv_sec, tv_nsec)
```

Update `convert_value_for_opcua()`:

```python
elif datatype.upper() == "TIME":
    # TIME values are stored as IEC_TIMESPEC (tv_sec, tv_nsec)
    # Convert to milliseconds for OPC-UA Int64 representation
    if isinstance(value, tuple) and len(value) == 2:
        tv_sec, tv_nsec = value
        return timespec_to_milliseconds(tv_sec, tv_nsec)
    elif isinstance(value, int):
        # Already in raw format, interpret as packed 64-bit value
        tv_sec = value & 0xFFFFFFFF
        tv_nsec = (value >> 32) & 0xFFFFFFFF
        return timespec_to_milliseconds(tv_sec, tv_nsec)
    return 0
```

Update `convert_value_for_plc()`:

```python
elif datatype.upper() == "TIME":
    # Convert OPC-UA milliseconds to IEC_TIMESPEC format
    ms = int(value)
    tv_sec, tv_nsec = milliseconds_to_timespec(ms)
    # Return as tuple for memory writing
    return (tv_sec, tv_nsec)
```

#### Task 1.4: Implement TIME Memory Read/Write

**File:** `core/src/drivers/plugins/python/opcua/opcua_memory.py`

```python
def read_timespec_direct(address: int) -> tuple[int, int]:
    """
    Read an IEC_TIMESPEC directly from memory.

    Returns:
        Tuple of (tv_sec, tv_nsec)
    """
    ptr = ctypes.cast(address, ctypes.POINTER(IEC_TIMESPEC))
    timespec = ptr.contents
    return (timespec.tv_sec, timespec.tv_nsec)

def write_timespec_direct(address: int, tv_sec: int, tv_nsec: int) -> bool:
    """
    Write an IEC_TIMESPEC to memory.
    """
    ptr = ctypes.cast(address, ctypes.POINTER(IEC_TIMESPEC))
    ptr.contents.tv_sec = tv_sec
    ptr.contents.tv_nsec = tv_nsec
    return True
```

Update `read_memory_direct()` to handle TIME size:

```python
def read_memory_direct(address: int, size: int, datatype: str = None) -> Any:
    """Read value from memory with optional datatype hint."""
    # ... existing code ...
    elif size == 8:
        if datatype and datatype.upper() in ["TIME", "DATE", "TOD", "DT"]:
            return read_timespec_direct(address)
        else:
            ptr = ctypes.cast(address, ctypes.POINTER(ctypes.c_uint64))
            return ptr.contents.value
```

### Phase 2: Synchronization Integration

#### Task 2.1: Update Address Space Creation

**File:** `core/src/drivers/plugins/python/opcua/address_space.py`

Ensure TIME variables are created with proper OPC-UA type and initial value conversion.

#### Task 2.2: Update Synchronization Logic

**File:** `core/src/drivers/plugins/python/opcua/synchronization.py`

Modify the sync functions to pass datatype information for proper TIME handling:

- `_sync_single_var_from_runtime()`: Pass datatype to memory read
- `_sync_single_var_to_runtime()`: Handle TIME tuple values for memory write

### Phase 3: Configuration and Validation

#### Task 3.1: Update Configuration Model

**File:** `core/src/drivers/plugins/python/shared/plugin_config_decode/opcua_config_model.py`

Add validation for TIME datatype:

```python
VALID_DATATYPES = ["BOOL", "BYTE", "INT", "DINT", "LINT", "FLOAT", "REAL",
                   "STRING", "TIME", "DATE", "TOD", "DT"]
```

#### Task 3.2: Update Type Inference

**File:** `core/src/drivers/plugins/python/opcua/opcua_utils.py`

Update `infer_var_type()` to better handle ambiguous sizes when datatype is known:

```python
def infer_var_type(size: int, configured_type: str = None) -> str:
    """Infer variable type from size and optional configured type."""
    if configured_type:
        return configured_type.upper()
    # ... existing inference logic ...
```

#### Task 3.3: Update Configuration Templates

**File:** `core/src/drivers/plugins/python/opcua/opcua_config_template.json`

Add TIME variable examples:

```json
{
    "node_id": "ns=2;s=CycleTime",
    "browse_name": "CycleTime",
    "display_name": "Cycle Time",
    "datatype": "TIME",
    "initial_value": 0,
    "description": "PLC scan cycle time",
    "index": 10,
    "permissions": {
        "viewer": "r",
        "operator": "r",
        "engineer": "rw"
    }
}
```

---

## Test Plan

### Unit Tests

#### Test Suite 1: Type Conversion (test_time_conversion.py)

```python
class TestTimeConversion:
    def test_timespec_to_milliseconds_basic(self):
        """Test basic conversion: 1 second = 1000 ms"""
        assert timespec_to_milliseconds(1, 0) == 1000

    def test_timespec_to_milliseconds_with_nanoseconds(self):
        """Test conversion with nanoseconds: 1.5 sec = 1500 ms"""
        assert timespec_to_milliseconds(1, 500_000_000) == 1500

    def test_milliseconds_to_timespec_basic(self):
        """Test reverse conversion"""
        assert milliseconds_to_timespec(1500) == (1, 500_000_000)

    def test_roundtrip_conversion(self):
        """Test roundtrip preserves value"""
        original = (5, 250_000_000)
        ms = timespec_to_milliseconds(*original)
        result = milliseconds_to_timespec(ms)
        assert result == original

    def test_zero_time(self):
        """Test zero value handling"""
        assert timespec_to_milliseconds(0, 0) == 0
        assert milliseconds_to_timespec(0) == (0, 0)

    def test_large_time_values(self):
        """Test large values (hours/days)"""
        # 24 hours in seconds = 86400
        ms = timespec_to_milliseconds(86400, 0)
        assert ms == 86_400_000
```

#### Test Suite 2: Type Mapping (test_time_mapping.py)

```python
class TestTimeTypeMapping:
    def test_time_maps_to_int64(self):
        """TIME should map to Int64"""
        assert map_plc_to_opcua_type("TIME") == ua.VariantType.Int64

    def test_time_case_insensitive(self):
        """Mapping should be case-insensitive"""
        assert map_plc_to_opcua_type("time") == ua.VariantType.Int64
        assert map_plc_to_opcua_type("Time") == ua.VariantType.Int64

    def test_date_maps_to_datetime(self):
        """DATE should map to DateTime"""
        assert map_plc_to_opcua_type("DATE") == ua.VariantType.DateTime
```

#### Test Suite 3: Memory Access (test_time_memory.py)

```python
class TestTimeMemoryAccess:
    def test_read_timespec_structure(self):
        """Test reading IEC_TIMESPEC from memory"""
        # Create test memory with known values
        test_struct = IEC_TIMESPEC()
        test_struct.tv_sec = 10
        test_struct.tv_nsec = 500_000_000

        address = ctypes.addressof(test_struct)
        result = read_timespec_direct(address)
        assert result == (10, 500_000_000)

    def test_write_timespec_structure(self):
        """Test writing IEC_TIMESPEC to memory"""
        test_struct = IEC_TIMESPEC()
        address = ctypes.addressof(test_struct)

        write_timespec_direct(address, 5, 250_000_000)

        assert test_struct.tv_sec == 5
        assert test_struct.tv_nsec == 250_000_000
```

### Integration Tests

#### Test Suite 4: End-to-End TIME Variable Sync (test_time_sync_integration.py)

```python
class TestTimeVariableSync:
    @pytest.fixture
    def time_variable_config(self):
        """Configuration with TIME variable"""
        return {
            "node_id": "ns=2;s=TestTime",
            "browse_name": "TestTime",
            "display_name": "Test Time Variable",
            "datatype": "TIME",
            "initial_value": 0,
            "description": "Test TIME variable",
            "index": 100,
            "permissions": {"viewer": "r", "operator": "rw", "engineer": "rw"}
        }

    async def test_time_variable_created_in_address_space(self, server, config):
        """Verify TIME variable is created with correct OPC-UA type"""
        # Create variable
        # Check node exists and has Int64 data type
        pass

    async def test_time_value_sync_plc_to_opcua(self, server, config):
        """Test syncing TIME value from PLC to OPC-UA"""
        # Set PLC memory to specific TIME value
        # Trigger sync
        # Verify OPC-UA node has correct milliseconds value
        pass

    async def test_time_value_sync_opcua_to_plc(self, server, config):
        """Test syncing TIME value from OPC-UA to PLC"""
        # Write milliseconds value to OPC-UA node
        # Trigger sync
        # Verify PLC memory has correct tv_sec/tv_nsec
        pass
```

#### Test Suite 5: Configuration Validation (test_time_config_validation.py)

```python
class TestTimeConfigValidation:
    def test_time_datatype_accepted(self):
        """TIME datatype should be valid in config"""
        config = {"datatype": "TIME", ...}
        # Should not raise
        SimpleVariable.from_dict(config)

    def test_time_initial_value_formats(self):
        """Various initial value formats for TIME"""
        # Integer milliseconds
        config1 = {"datatype": "TIME", "initial_value": 5000, ...}
        # String format "T#5s"
        config2 = {"datatype": "TIME", "initial_value": "T#5s", ...}
```

### System Tests

#### Test Suite 6: OPC-UA Client Interaction (test_time_client.py)

```python
class TestTimeWithOpcuaClient:
    async def test_read_time_value_with_uaexpert(self):
        """Verify TIME value can be read by standard OPC-UA client"""
        # Start server with TIME variable
        # Connect with asyncua client
        # Read value, verify it's Int64 type with correct value
        pass

    async def test_write_time_value_with_uaexpert(self):
        """Verify TIME value can be written by standard OPC-UA client"""
        # Write Int64 value representing milliseconds
        # Verify PLC memory updated correctly
        pass

    async def test_time_subscription_updates(self):
        """Verify TIME variable changes trigger subscriptions"""
        # Subscribe to TIME node
        # Change PLC value
        # Verify subscription callback received
        pass
```

### Performance Tests

#### Test Suite 7: TIME Sync Performance (test_time_performance.py)

```python
class TestTimePerformance:
    def test_time_conversion_performance(self):
        """Conversion should be fast"""
        import timeit
        time_taken = timeit.timeit(
            lambda: timespec_to_milliseconds(12345, 678_000_000),
            number=100_000
        )
        assert time_taken < 1.0  # 100k conversions under 1 second

    def test_time_sync_latency(self):
        """Measure sync latency for TIME variables"""
        # Time the complete sync cycle
        pass
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `core/src/drivers/plugins/python/opcua/opcua_utils.py` | Add TIME mapping, conversion functions |
| `core/src/drivers/plugins/python/opcua/opcua_memory.py` | Add IEC_TIMESPEC struct, read/write functions |
| `core/src/drivers/plugins/python/opcua/address_space.py` | Handle TIME in variable creation |
| `core/src/drivers/plugins/python/opcua/synchronization.py` | Pass datatype for TIME handling |
| `core/src/drivers/plugins/python/shared/plugin_config_decode/opcua_config_model.py` | Add TIME validation |
| `core/src/drivers/plugins/python/opcua/opcua_config_template.json` | Add TIME examples |
| `core/src/drivers/plugins/python/opcua/docs/` | Update documentation |

## New Files to Create

| File | Purpose |
|------|---------|
| `tests/plugins/opcua/test_time_conversion.py` | Unit tests for conversion |
| `tests/plugins/opcua/test_time_mapping.py` | Unit tests for type mapping |
| `tests/plugins/opcua/test_time_memory.py` | Unit tests for memory access |
| `tests/plugins/opcua/test_time_sync_integration.py` | Integration tests |

---

## Implementation Priority

1. **High Priority (Core Functionality)**
   - Task 1.1: IEC_TIMESPEC ctypes structure
   - Task 1.2: Type mapping
   - Task 1.3: Conversion functions
   - Task 1.4: Memory read/write

2. **Medium Priority (Integration)**
   - Task 2.1: Address space creation
   - Task 2.2: Synchronization logic

3. **Lower Priority (Polish)**
   - Task 3.1: Configuration validation
   - Task 3.2: Type inference update
   - Task 3.3: Template and documentation updates

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Precision loss (ns to ms) | Low | Document limitation; sufficient for most PLC applications |
| Breaking existing configs | Medium | TIME is opt-in via explicit datatype |
| Memory alignment issues | High | Use ctypes Structure with matching C layout |
| OPC-UA client compatibility | Medium | Use standard Int64 type; test with multiple clients |

---

## Acceptance Criteria

1. TIME variables can be configured in opcua.json
2. TIME values sync correctly PLC -> OPC-UA (ms representation)
3. TIME values sync correctly OPC-UA -> PLC (timespec structure)
4. Standard OPC-UA clients can read/write TIME values
5. All unit and integration tests pass
6. No regression in existing type support
7. Documentation updated with TIME examples

---

## Future Considerations

- **LTIME support**: IEC 61131-3 LTIME (64-bit time) may use different structure
- **DATE/DT/TOD types**: Can use same IEC_TIMESPEC structure with DateTime mapping
- **LREAL support**: Similar pattern (8-byte, needs struct unpacking)
- **Array of TIME**: Extend array support to handle TIME arrays
