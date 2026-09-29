export type DischargeData = {
  id: number;
  patient_code: string | null;
  patient_name: string;
  age: number | null;
  gender: string | null;
  doctor_name: string | null;
  doctor_specialization: string | null;
  status: string;
  diagnosis: string | null;
  medication: string | null;
  amount: number | null;
  admission_date: string | null;
  discharge_date: string | null;
  approved_by: string | null;
};

const v = (x: unknown) => (x === null || x === undefined || x === "" ? "—" : String(x));

export default function DischargeSheet({ d }: { d: DischargeData }) {
  return (
    <div className="discharge-sheet">
      <h2>DISCHARGE SUMMARY</h2>
      <div className="sub">
        Helio Hospital Operations · Status: {d.status}
        {d.status !== "APPROVED" && " (draft — not valid until approved by a doctor)"}
      </div>
      <table>
        <tbody>
          <tr><td>Patient ID</td><td>{v(d.patient_code)}</td></tr>
          <tr><td>Patient Name</td><td>{v(d.patient_name)}</td></tr>
          <tr><td>Age / Gender</td><td>{v(d.age)} / {v(d.gender)}</td></tr>
          <tr><td>Date of Admission</td><td>{v(d.admission_date)}</td></tr>
          <tr><td>Date of Discharge</td><td>{v(d.discharge_date)}</td></tr>
          <tr>
            <td>Responsible Doctor</td>
            <td>{v(d.doctor_name)}{d.doctor_specialization ? ` (${d.doctor_specialization})` : ""}</td>
          </tr>
          <tr><td>Diagnosis</td><td>{v(d.diagnosis)}</td></tr>
          <tr><td>Medication Taken</td><td><pre>{v(d.medication)}</pre></td></tr>
          <tr><td>Amount (₹)</td><td>{d.amount === null ? "Not entered" : `₹ ${d.amount.toFixed(2)}`}</td></tr>
          <tr><td>Approved By</td><td>{d.status === "APPROVED" ? v(d.approved_by) : "Pending doctor approval"}</td></tr>
        </tbody>
      </table>
    </div>
  );
}
