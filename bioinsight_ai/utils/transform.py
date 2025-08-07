import pandas as pd

def transform_wide_to_long(wide_csv_path: str, long_csv_path: str):
    """
    Reads a wide-format gene expression CSV,
    pivots only numeric gene columns to long-form,
    and saves as long CSV.
    """

    df = pd.read_csv(wide_csv_path)

    # Define known metadata columns to exclude
    metadata_cols = [
        "sample_id", "Sample_Index", "case_submitter_id",
        "tumor_stage", "tumor_grade", "primary_diagnosis", "morphology"
    ]

    # Figure out your index column for melting (e.g. Sample_Index)
    id_vars = ["Sample_Index"]

    # Everything else that is numeric and not in metadata is a gene
    gene_cols = [
        col for col in df.columns
        if col not in metadata_cols and
           pd.api.types.is_numeric_dtype(df[col])
    ]

    # 📝 DEBUG: Log what you’re melting
    print(f"[transform_wide_to_long] Found gene columns: {gene_cols}")

    # Melt to long-form
    long_df = pd.melt(
        df,
        id_vars=id_vars,
        value_vars=gene_cols,
        var_name="Gene",
        value_name="Expression"
    )

    long_df.to_csv(long_csv_path, index=False)
    print(f"[transform_wide_to_long] Long-form CSV saved to: {long_csv_path}")
