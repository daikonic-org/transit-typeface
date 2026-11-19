"""Recalibrate a font's point size while preserving its design units."""

from fontTools.misc.roundTools import otRound


NEW_POINT_SIZE = 12


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
