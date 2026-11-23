"""Recalibrate a font's point size while preserving its design units."""

from fontTools.misc.roundTools import otRound


NEW_POINT_SIZE = 12


def ensure_system_calibration(font):
    """Carry forward System's accepted 11-point cut at a nominal 12 points."""
    units = 1000
    factor = NEW_POINT_SIZE / 11
    if font["head"].unitsPerEm == units:
        recalibrate(font, 11)
    if font["head"].unitsPerEm != otRound(units * factor):
        raise ValueError("Expected a pre-calibration or calibrated System source")
    optical = next(axis for axis in font["fvar"].axes if axis.axisTag == "opsz")
    values = optical.minValue, optical.defaultValue, optical.maxValue
    if any(abs(value - size * factor) > 1 / 65536 for value, size in zip(values, (10, 14, 36))):
        raise ValueError("System optical coordinates must match the 12-point calibration")


def recalibrate(font, previous_point_size):
    factor = NEW_POINT_SIZE / previous_point_size
    font["head"].unitsPerEm = otRound(font["head"].unitsPerEm * factor)
    fvar = font["fvar"]
    opsz = next((axis for axis in fvar.axes if axis.axisTag == "opsz"), None)
    if opsz is None:
        return
    for field in ("minValue", "defaultValue", "maxValue"):
        setattr(opsz, field, factor * getattr(opsz, field))
    for instance in fvar.instances:
        instance.coordinates["opsz"] *= factor

    stat = font["STAT"].table
    axis_index = next(
        i for i, axis in enumerate(stat.DesignAxisRecord.Axis) if axis.AxisTag == "opsz"
    )
    for value in stat.AxisValueArray.AxisValue:
        if value.Format == 4:
            for axis in value.AxisValueRecord:
                if axis.AxisIndex == axis_index:
                    axis.Value *= factor
        elif value.AxisIndex == axis_index:
            fields = {
                1: ("Value",),
                2: ("NominalValue", "RangeMinValue", "RangeMaxValue"),
                3: ("Value", "LinkedValue"),
            }[value.Format]
            for field in fields:
                setattr(value, field, factor * getattr(value, field))
