using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;

internal static class GenerateWorkbenchIcon
{
    private static GraphicsPath RoundedRectangle(RectangleF bounds, float radius)
    {
        float diameter = radius * 2;
        GraphicsPath path = new GraphicsPath();
        path.AddArc(bounds.Left, bounds.Top, diameter, diameter, 180, 90);
        path.AddArc(bounds.Right - diameter, bounds.Top, diameter, diameter, 270, 90);
        path.AddArc(bounds.Right - diameter, bounds.Bottom - diameter, diameter, diameter, 0, 90);
        path.AddArc(bounds.Left, bounds.Bottom - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();
        return path;
    }

    private static Bitmap Draw(int size)
    {
        Bitmap bitmap = new Bitmap(size, size, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(bitmap))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            float s = size / 512f;
            RectangleF outer = new RectangleF(38 * s, 48 * s, 436 * s, 408 * s);
            using (GraphicsPath p = RoundedRectangle(outer, 72 * s))
            using (LinearGradientBrush brush = new LinearGradientBrush(outer, Color.FromArgb(22,119,255), Color.FromArgb(8,71,166), 45f))
                g.FillPath(brush, p);

            RectangleF screen = new RectangleF(69 * s, 79 * s, 374 * s, 346 * s);
            using (GraphicsPath p = RoundedRectangle(screen, 43 * s)) g.FillPath(new SolidBrush(Color.FromArgb(7,27,56)), p);
            using (SolidBrush white = new SolidBrush(Color.FromArgb(243,248,255)))
                g.FillRectangle(white, 69*s, 108*s, 374*s, 35*s);
            g.FillEllipse(Brushes.OrangeRed, 100*s, 100*s, 22*s, 22*s);
            g.FillEllipse(Brushes.Gold, 135*s, 100*s, 22*s, 22*s);
            g.FillEllipse(Brushes.LimeGreen, 170*s, 100*s, 22*s, 22*s);

            float divider = Math.Max(1.5f, 13*s);
            using (Pen pen = new Pen(Color.FromArgb(64,150,255), divider))
            {
                g.DrawLine(pen, 256*s, 143*s, 256*s, 425*s);
                g.DrawLine(pen, 69*s, 284*s, 443*s, 284*s);
            }
            float mark = Math.Max(1.7f, 18*s);
            using (Pen pen = new Pen(Color.White, mark))
            {
                pen.StartCap = pen.EndCap = LineCap.Round;
                pen.LineJoin = LineJoin.Round;
                g.DrawLines(pen, new[] { new PointF(111*s,205*s), new PointF(156*s,240*s), new PointF(111*s,275*s) });
                g.DrawLine(pen, 173*s, 276*s, 228*s, 276*s);
            }
        }
        return bitmap;
    }

    private static byte[] Png(Bitmap bitmap)
    {
        using (MemoryStream stream = new MemoryStream())
        {
            bitmap.Save(stream, ImageFormat.Png);
            return stream.ToArray();
        }
    }

    private static void Main(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("Usage: GenerateWorkbenchIcon output.ico preview.png");
        int[] sizes = { 16, 20, 24, 32, 40, 48, 64, 128, 256 };
        List<byte[]> images = new List<byte[]>();
        foreach (int size in sizes) using (Bitmap bitmap = Draw(size)) images.Add(Png(bitmap));
        using (Bitmap preview = Draw(512)) preview.Save(args[1], ImageFormat.Png);

        using (BinaryWriter writer = new BinaryWriter(File.Create(args[0])))
        {
            writer.Write((ushort)0); writer.Write((ushort)1); writer.Write((ushort)sizes.Length);
            int offset = 6 + sizes.Length * 16;
            for (int i = 0; i < sizes.Length; i++)
            {
                writer.Write((byte)(sizes[i] == 256 ? 0 : sizes[i]));
                writer.Write((byte)(sizes[i] == 256 ? 0 : sizes[i]));
                writer.Write((byte)0); writer.Write((byte)0); writer.Write((ushort)1); writer.Write((ushort)32);
                writer.Write(images[i].Length); writer.Write(offset); offset += images[i].Length;
            }
            foreach (byte[] image in images) writer.Write(image);
        }
    }
}
