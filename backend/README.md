# HR Requests App

This local Next.js app serves the existing HR Portal UI from `public/index.html` at `/`. The leave and remote-work modals use the backend request endpoints. It reads employee names from the first column of local-data/employees-and-remote-work.xlsx. Leave requests fill local-data/leave-request-template.docx. Remote-work requests update a copy of the Excel workbook and return it for download.

## Local setup

1. Use Node.js 20.9 or later.
2. Open a terminal in the backend folder.
3. Run npm install, then npm run dev.
4. Open http://localhost:3000.

The supplied Excel file currently contains the headers “Ονοματεπώνυμο” and “remote work dates” but no employee rows. Add employee names below the first header, starting at A2, in backend/local-data/employees-and-remote-work.xlsx, save the file, and refresh the app.

The app does not change the source templates. Every request returns a newly generated copy for download. Leave days are counted Monday through Friday; public holidays are not excluded because no holiday calendar was supplied. The employee and management signature fields in the leave form stay blank.
