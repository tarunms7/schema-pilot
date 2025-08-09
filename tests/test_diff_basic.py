from schema_agent.core.ir import IR, Table, Column
from schema_agent.core.diff import diff_ir, OpKind


def make_ir():
    base = IR(
        dialect="postgresql",
        tables={
            "orders": Table(
                name="orders",
                columns={
                    "id": Column(name="id", data_type="bigint", nullable=False),
                    "total_price": Column(name="total_price", data_type="numeric(12,2)", nullable=True),
                    "status": Column(name="status", data_type="text", nullable=False, default="'pending'"),
                },
                primary_key=["id"],
            )
        },
    )
    head = IR(
        dialect="postgresql",
        tables={
            "orders": Table(
                name="orders",
                columns={
                    "id": Column(name="id", data_type="bigint", nullable=False),
                    "amount": Column(name="amount", data_type="numeric(12,2)", nullable=False, default="0"),
                    "status": Column(name="status", data_type="text", nullable=False, default="'pending'"),
                },
                primary_key=["id"],
            )
        },
    )
    return base, head


def test_diff_rename_and_constraints():
    base, head = make_ir()
    ops = diff_ir(base, head, hints={"renames": {"orders.total_price": "orders.amount"}})
    kinds = [op.kind for op in ops]
    assert OpKind.RENAME_COLUMN in kinds
    assert OpKind.ALTER_NULLABLE in kinds
    assert OpKind.ALTER_DEFAULT in kinds


