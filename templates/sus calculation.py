# =========================================
# SUS Calculation + Auto-LaTeX Output
# =========================================

import pandas as pd
import numpy as np
from textwrap import dedent

# Load your Excel file
file_path = "Interview Result Data- Final Priority.xlsx"
survey_data = pd.read_excel(file_path, sheet_name='Survey Results')

# Extract SUS-related columns (as you specified)
sus_data = survey_data.iloc[1:, [3, 6, 9, 12, 14]].copy()
sus_data.columns = ['Q1', 'Q2', 'Q3', 'Q4', 'SUS_Score']

# Convert to numeric and drop missing SUS scores
sus_data = sus_data.apply(pd.to_numeric, errors='coerce').dropna(subset=['SUS_Score'])

# Compute core statistics
n = len(sus_data)
mean_sus = sus_data['SUS_Score'].mean()
sd_sus = sus_data['SUS_Score'].std(ddof=1)
se_sus = sd_sus / np.sqrt(n)
ci_low = mean_sus - 1.96 * se_sus
ci_high = mean_sus + 1.96 * se_sus

# Now generate LaTeX block (make sure variables exist before this point)
latex_text = dedent(f"""
System Usability Scale (SUS) computation

SUS was scored using the canonical Brooke (1996) algorithm. For respondent $i$ and item $j$ (1–10) on a 1–5 Likert scale:

$$
c_{{ij}} = 
\\begin{{cases}}
x_{{ij}} - 1, & \\text{{if }} j \\text{{ is odd}} \\\\
5 - x_{{ij}}, & \\text{{if }} j \\text{{ is even}}
\\end{{cases}}
$$

The per-respondent SUS is:
$$
S_i = 2.5 \\sum_{{j=1}}^{{10}} c_{{ij}}, \\quad \\text{{range }} 0–100
$$

The study-level mean SUS is:
$$
\\bar{{S}} = \\frac{{1}}{{n}}\\sum_{{i=1}}^{{n}} S_i
$$

From the observed data ($n = {n}$ participants):
$$
\\bar{{S}} = {mean_sus:.2f}, \\quad SD = {sd_sus:.2f}, \\quad SE = {se_sus:.2f}, \\quad 95\\%\\,CI = [{ci_low:.2f},\\;{ci_high:.2f}]
$$

Between-group comparisons (patients vs. care partners) were evaluated using a Mann–Whitney $U$ test when normality was not met; otherwise, a two-sample $t$ test with Welch correction was applied.
""")

# Print the LaTeX-formatted text
print(latex_text)
